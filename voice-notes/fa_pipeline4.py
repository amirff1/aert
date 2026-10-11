#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_pipeline4 — رأی‌گیری شش‌جریانی (ROVER+): افزودن کانال‌های مستقل تر
====================================================================
جریان‌ها: A) afftdn+loudnorm/fa042  B) peak+RNNoise/fa042  C) peak+RNNoise/fa05
         D) afftdn+loudnorm/fa05   E) peak-only/fa042     F) Hush(DF3)/fa042
چهار جریانِ مستقل روی هر کلیپ اجرا می‌شود:
   A) afftdn+loudnorm          → Vosk small-fa-0.42
   B) peak-norm + RNNoise      → Vosk small-fa-0.42
   C) peak-norm + RNNoise      → Vosk small-fa-0.5
   D) afftdn+loudnorm          → Vosk small-fa-0.5
سپس واژه‌های هر چهار جریان با «مهر زمانی» در اسلات‌های زمانی هم‌تراز می‌شوند و
هر اسلات با اکثریتِ آراء و سپس اطمینان انتخاب می‌شود (ROVER ساده‌شده).
واژهٔ مورد توافق دو/سه/چهار جریان، بسیار محتمل‌تر درست است.

خروجی: work/zadkamali/fa4_out/<media>.json  (words + votes + text)
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time, wave
import numpy as np, soundfile as sf

sys.path.insert(0, '/home/user/aert/voice-notes')
from rnnoise_dn import denoise_array

from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)

FF = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
WORK = '/home/user/work/zadkamali'
OUT = f'{WORK}/fa4_out'
os.makedirs(OUT, exist_ok=True)
MODELS = {
    'fa042': '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42',
    'fa05': '/home/user/asr-models/vosk-fa2',
}
GAP = 0.32        # فاصلهٔ زمانی مرکز واژه‌ها برای شروع اسلات جدید (ثانیه)
MIN_SUPPORT = 0.0  # آستانهٔ اطمینان برای واژه‌های تک‌رأی (۰ = همه حفظ شوند)


# ------------------------------------------------------------------ پیش‌پردازش
def ff(src, dst, af=None):
    cmd = [FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src]
    if af:
        cmd += ['-af', af]
    cmd += ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst]
    subprocess.run(cmd, check=True)


def prep_old(src, dst):
    ff(src, dst, 'afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11')


def prep_peak(src, dst):
    """فقط پیک‌نرمال (بدون نویزگیری) — کانال مستقل سوم"""
    tmp = dst + '.t.wav'
    ff(src, tmp)
    x, sr = sf.read(tmp, dtype='float32')
    m = float(abs(x).max())
    if m > 1e-6:
        x = np.clip(x * (10 ** (-1.0 / 20) / m), -1, 1)
    sf.write(dst, x, sr, subtype='PCM_16')
    os.path.exists(tmp) and os.remove(tmp)


def prep_hush(src, dst):
    """نویزگیر عصبی DeepFilterNet3 (Hush) — کانال مستقل چهارم"""
    from hush_denoise import denoise_array as hush_dn
    tmp = dst + '.t.wav'
    ff(src, tmp)
    x, sr = sf.read(tmp, dtype='float32')
    m = float(abs(x).max())
    if m > 1e-6:
        x = np.clip(x * (10 ** (-1.0 / 20) / m), -1, 1)
    sf.write(tmp, x, sr, subtype='PCM_16')
    xi, _ = sf.read(tmp, dtype='int16')
    y = hush_dn(xi, sr, df_mode='sub')
    # بازگرداندن سطح: Hush سطح را ~۱۱ برابر کم می‌کند؛ پیک‌نرمال دوباره
    yf = y.astype(np.float32) / 32768.0
    mm = float(abs(yf).max())
    if mm > 1e-6:
        yf = np.clip(yf * (10 ** (-1.0 / 20) / mm), -1, 1)
    sf.write(dst, (yf * 32767).astype(np.int16), sr, subtype='PCM_16')
    os.path.exists(tmp) and os.remove(tmp)


def prep_new(src, dst):
    """peak→−1dBFS + RNNoise (برندهٔ A/B نسخهٔ ۲)"""
    tmp = dst + '.t.wav'
    ff(src, tmp)
    x, sr = sf.read(tmp, dtype='float32')
    m = float(abs(x).max())
    if m > 1e-6:
        x = np.clip(x * (10 ** (-1.0 / 20) / m), -1, 1)
    sf.write(tmp, x, sr, subtype='PCM_16')
    xi, _ = sf.read(tmp, dtype='int16')
    try:
        sf.write(dst, denoise_array(xi, sr), sr, subtype='PCM_16')
    except Exception as e:
        print('  rnnoise warn:', e, file=sys.stderr)
        os.replace(tmp, dst)
        return
    os.remove(tmp)


# ------------------------------------------------------------------ ASR
def vosk_words(model, wav):
    wf = wave.open(wav, 'rb')
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    words, segs = [], []
    while True:
        b = wf.readframes(4000)
        if not b:
            break
        if rec.AcceptWaveform(b):
            r = json.loads(rec.Result())
            if r.get('result'):
                words += r['result']
                segs.append({'t0': r['result'][0]['start'], 't1': r['result'][-1]['end'],
                             'text': r['text']})
    r = json.loads(rec.FinalResult())
    if r.get('result'):
        words += r['result']
        segs.append({'t0': r['result'][0]['start'], 't1': r['result'][-1]['end'],
                     'text': r['text']})
    return words, segs


# ------------------------------------------------------------------ ROVER
_PAR_MAP = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'آ': 'آ',
                          'ٱ': 'ا', 'ؤ': 'و', 'ئ': 'ی', '٠': '۰', '1': '۱', '2': '۲',
                          '3': '۳', '4': '۴', '5': '۵', '6': '۶', '7': '۷', '8': '۸',
                          '9': '۹', '0': '۰'})


def norm_w(t: str) -> str:
    t = t.translate(_PAR_MAP)
    t = re.sub(r'[\u064B-\u0652\u200c\u200f\u200e]', '', t)   # اعراب و نیم‌فاصله
    t = re.sub(r'[^\u0600-\u06FF۰-۹]+', '', t)
    return t


def rover(streams: dict[str, list[dict]]) -> list[dict]:
    """هم‌ترازی واژه‌به‌واژه با «جریان مرجع» + رأی‌گیری (ROVER)

    جریان مرجع = جریانی با بیشترین تعداد واژه. برای هر واژهٔ مرجع یک اسلات ساخته
    می‌شود و از هر جریان دیگر حداکثر یک واژه (با بیشترین هم‌پوشانی زمانی) در آن
    اسلات قرار می‌گیرد. سپس رأی‌گیری. واژه‌های جاماندهٔ سایر جریان‌ها که با هیچ
    اسلاتی هم‌پوشانی ندارند، در پایان (با رأی ۱) افزوده می‌شوند تا فراخوانی بالا بماند.
    """
    names = list(streams)
    if not any(streams.values()):
        return []
    ref_name = max(names, key=lambda k: len(streams[k]))
    ref = streams[ref_name]
    used = {k: [False] * len(streams[k]) for k in names}
    slots: list[dict] = []

    for ri, rw in enumerate(ref):
        slot = {ref_name: rw}
        used[ref_name][ri] = True
        rc = (rw['start'] + rw['end']) / 2.0
        dur = rw['end'] - rw['start']
        tol = max(0.28, dur / 2.0 + 0.10)
        for k in names:
            if k == ref_name:
                continue
            best, bi, best_ov = None, -1, None
            for j, w in enumerate(streams[k]):
                if used[k][j]:
                    continue
                wc = (w['start'] + w['end']) / 2.0
                if abs(wc - rc) > tol:
                    continue
                ov = min(rw['end'], w['end']) - max(rw['start'], w['start'])
                if best is None or ov > best_ov:
                    best, bi, best_ov = w, j, ov
            if best is not None:
                slot[k] = best
                used[k][bi] = True
        slots.append(slot)

    # --- واژه‌های جامانده: اگر با هیچ اسلاتی هم‌پوشانی ندارند، افزوده شوند
    spans = [(min(w['start'] for w in sl.values()), max(w['end'] for w in sl.values()))
             for sl in slots]
    leftovers = []
    for k in names:
        for j, w in enumerate(streams[k]):
            if used[k][j]:
                continue
            if any(not (w['end'] < a or w['start'] > b) for a, b in spans):
                continue
            leftovers.append((k, w))
    leftovers.sort(key=lambda kv: kv[1]['start'])
    for k, w in leftovers:
        slots.append({k: w})
    slots.sort(key=lambda sl: min(w['start'] for w in sl.values()))

    def vote(slot: dict) -> dict | None:
        votes: dict[str, dict] = {}
        for name, w in slot.items():
            key = norm_w(w['word'])
            if not key:
                continue
            d = votes.setdefault(key, {'text': w['word'], 'streams': set(), 'confs': [],
                                       'start': w['start'], 'end': w['end']})
            d['streams'].add(name)
            d['confs'].append(w['conf'])
            d['start'] = min(d['start'], w['start'])
            d['end'] = max(d['end'], w['end'])
        if not votes:
            return None

        def key(kv):
            k, d = kv
            return (len(d['streams']), round(float(np.mean(d['confs'])), 4), len(k))
        best_k, best = max(votes.items(), key=key)
        return {'word': best['text'], 'norm': best_k, 'votes': len(best['streams']),
                'conf': round(float(np.mean(best['confs'])), 3),
                'start': round(best['start'], 2), 'end': round(best['end'], 2),
                'alts': [{'w': k, 'v': len(d['streams']),
                          'c': round(float(np.mean(d['confs'])), 3)}
                         for k, d in sorted(votes.items(), key=key, reverse=True)
                         if k != best_k][:3]}

    merged = [m for m in (vote(sl) for sl in slots) if m]
    out = []
    for w in merged:
        if out and out[-1]['norm'] == w['norm']:
            out[-1]['votes'] = max(out[-1]['votes'], w['votes'])
            continue
        out.append(w)
    return out


# ------------------------------------------------------------------ main
def main():
    files = sorted([f for f in os.listdir(f'{WORK}/audio') if f.endswith('.m4a')],
                   key=lambda x: int(re.search(r'(\d+)', x).group(1)))
    loaded = {k: Model(p) for k, p in MODELS.items()}
    print('models loaded', flush=True)
    summary = {}
    for i, f in enumerate(files, 1):
        name = f[:-4]
        src = f'{WORK}/audio/{f}'
        wo, wn = f'/tmp/{name}_old.wav', f'/tmp/{name}_new.wav'
        wp, wh = f'/tmp/{name}_peak.wav', f'/tmp/{name}_hush.wav'
        t0 = time.time()
        prep_old(src, wo)
        prep_new(src, wn)
        prep_peak(src, wp)
        try:
            prep_hush(src, wh)
            have_hush = True
        except Exception as e:
            print('  hush warn:', e, file=sys.stderr)
            have_hush = False
        streams = {
            'old_fa042': vosk_words(loaded['fa042'], wo)[0],
            'new_fa042': vosk_words(loaded['fa042'], wn)[0],
            'new_fa05': vosk_words(loaded['fa05'], wn)[0],
            'old_fa05': vosk_words(loaded['fa05'], wo)[0],
            'peak_fa042': vosk_words(loaded['fa042'], wp)[0],
        }
        if have_hush:
            streams['hush_fa042'] = vosk_words(loaded['fa042'], wh)[0]
        os.makedirs(f'{OUT}/streams', exist_ok=True)
        json.dump({k: v for k, v in streams.items()},
                  open(f'{OUT}/streams/{name}.json', 'w'), ensure_ascii=False)
        merged = rover(streams)
        text = ' '.join(w['word'] for w in merged)
        agree2 = sum(1 for w in merged if w['votes'] >= 2)
        agree3 = sum(1 for w in merged if w['votes'] >= 3)
        json.dump({'media': name, 'text': text, 'words': merged,
                   'streams': {k: len(v) for k, v in streams.items()},
                   'stats': {'n_words': len(merged), 'vote2plus': agree2,
                             'vote3plus': agree3,
                             'agree_ratio': round(agree2 / max(1, len(merged)), 3)}},
                  open(f'{OUT}/{name}.json', 'w'), ensure_ascii=False, indent=1)
        open(f'{OUT}/{name}.txt', 'w').write(text + '\n')
        summary[name] = dict(n_words=len(merged), vote2plus=agree2, vote3plus=agree3,
                             agree=round(agree2 / max(1, len(merged)), 3),
                             chars=len(text), secs=round(time.time() - t0, 1))
        print(f"[{i:2d}/{31}] {name:9s} واژه={len(merged):4d} توافق≥۲: {agree2:4d} "
              f"({agree2/max(1,len(merged)):.0%})  [{time.time()-t0:5.1f}s]", flush=True)
        for f_ in (wo, wn, wp, wh):
            os.path.exists(f_) and os.remove(f_)
    json.dump(summary, open(f'{OUT}/_summary.json', 'w'), ensure_ascii=False, indent=1)
    tot = sum(v['n_words'] for v in summary.values())
    ag = sum(v['vote2plus'] for v in summary.values())
    print(f'\nمجموع واژه‌ها: {tot} | با توافق ≥۲ جریان: {ag} ({ag/max(1,tot):.1%})')
    print('FA3_PIPELINE_DONE', flush=True)


if __name__ == '__main__':
    main()
