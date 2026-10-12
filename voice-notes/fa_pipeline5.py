#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_pipeline5 — جریان‌های تازهٔ پیش‌پردازش گفتارِ کم‌جان + رأی‌گیری (ROVER)
=====================================================================
هدف: وفاداری بیشتر متن به صدای استاد با کانال‌های مستقلِ جدید.

جریان‌ها (هر کدام یک کانال مستقل برای رأی‌گیری):
  S1: speechnorm (نرمال‌سازی مخصوص گفتار ffmpeg)          → Vosk small-fa-0.42
  S2: dynaudnorm (نرمال‌سازی دینامیک کوتاه‌مدت)            → Vosk small-fa-0.5
  S3: peak(−1dBFS) + RNNoise (کانال اثبات‌شدهٔ نسل قبل)   → Vosk small-fa-0.42
  S4: afftdn+loudnorm (کانال اثبات‌شدهٔ نسل قبل)           → Vosk small-fa-0.5

خروجی: work/zadkamali/fa5_out/<media>.json  (+ streams/ برای بازرأی‌گیری)
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time, wave
import numpy as np, soundfile as sf

sys.path.insert(0, '/home/user/aert/voice-notes')
from rnnoise_dn import denoise_array

from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)

FF = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
import glob as _g
if not os.path.exists(FF):
    cands = _g.glob('/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-*')
    FF = cands[0] if cands else 'ffmpeg'

WORK = '/home/user/work/zadkamali'
OUT = f'{WORK}/fa5_out'
os.makedirs(f'{OUT}/streams', exist_ok=True)
MODELS = {
    'fa042': '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42',
    'fa05': '/home/user/asr-models/vosk-fa2',
}

_PAR_MAP = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا',
                          'ؤ': 'و', 'ئ': 'ی', '٠': '۰', '1': '۱', '2': '۲',
                          '3': '۳', '4': '۴', '5': '۵', '6': '۶', '7': '۷',
                          '8': '۸', '9': '۹', '0': '۰'})


def norm_w(t: str) -> str:
    t = t.translate(_PAR_MAP)
    t = re.sub(r'[\u064B-\u0652\u200c\u200f\u200e]', '', t)
    return re.sub(r'[^\u0600-\u06FF۰-۹]+', '', t)


def ff(src, dst, af=None):
    cmd = [FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src]
    if af:
        cmd += ['-af', af]
    cmd += ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- پیش‌پردازش‌ها
def prep_speechnorm(src, dst):
    ff(src, dst, 'speechnorm=e=12.5:r=0.0001:l=1')


def prep_dynaudnorm(src, dst):
    ff(src, dst, 'dynaudnorm=f=250:g=15:p=0.9')


def prep_afftdn(src, dst):
    ff(src, dst, 'afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11')


def prep_peak_rnnoise(src, dst):
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


STREAMS = [
    ('speechnorm_fa042', prep_speechnorm, 'fa042'),
    ('dynaudnorm_fa05', prep_dynaudnorm, 'fa05'),
    ('peakrn_fa042', prep_peak_rnnoise, 'fa042'),
    ('afftdn_fa05', prep_afftdn, 'fa05'),
]


def vosk_words(model, wav):
    wf = wave.open(wav, 'rb')
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    words = []
    while True:
        b = wf.readframes(4000)
        if not b:
            break
        if rec.AcceptWaveform(b):
            r = json.loads(rec.Result())
            words += r.get('result') or []
    r = json.loads(rec.FinalResult())
    words += r.get('result') or []
    return words


def rover(streams: dict[str, list[dict]]) -> list[dict]:
    """هم‌ترازی واژه‌به‌واژه با جریان مرجع + رأی‌گیری (ROVER)"""
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
        tol = max(0.28, (rw['end'] - rw['start']) / 2.0 + 0.10)
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

    def vote(slot: dict):
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
                'alts': [{'w': k, 'v': len(d['streams']), 'c': round(float(np.mean(d['confs'])), 3)}
                         for k, d in sorted(votes.items(), key=key, reverse=True) if k != best_k][:3]}

    merged = [m for m in (vote(sl) for sl in slots) if m]
    out = []
    for w in merged:
        if out and out[-1]['norm'] == w['norm']:
            out[-1]['votes'] = max(out[-1]['votes'], w['votes'])
            continue
        out.append(w)
    return out


def main():
    files = sorted([f for f in os.listdir(f'{WORK}/audio') if f.endswith('.m4a')],
                   key=lambda x: int(re.search(r'(\d+)', x).group(1)))
    loaded = {k: Model(p) for k, p in MODELS.items()}
    print('models loaded', flush=True)
    summary = {}
    for i, f in enumerate(files, 1):
        name = f[:-4]
        src = f'{WORK}/audio/{f}'
        t0 = time.time()
        streams = {}
        for sname, prep, mkey in STREAMS:
            wav = f'/tmp/{name}_{sname}.wav'
            try:
                prep(src, wav)
                streams[sname] = vosk_words(loaded[mkey], wav)
            except Exception as e:
                print(f'  {sname} warn:', e, file=sys.stderr)
                streams[sname] = []
            finally:
                os.path.exists(wav) and os.remove(wav)
        json.dump(streams, open(f'{OUT}/streams/{name}.json', 'w'), ensure_ascii=False)
        merged = rover(streams)
        text = ' '.join(w['word'] for w in merged)
        n2 = sum(1 for w in merged if w['votes'] >= 2)
        json.dump({'media': name, 'text': text, 'words': merged,
                   'streams': {k: len(v) for k, v in streams.items()},
                   'stats': {'n_words': len(merged), 'vote2plus': n2,
                             'agree_ratio': round(n2 / max(1, len(merged)), 3)}},
                  open(f'{OUT}/{name}.json', 'w'), ensure_ascii=False, indent=1)
        open(f'{OUT}/{name}.txt', 'w').write(text + '\n')
        summary[name] = dict(n_words=len(merged), vote2plus=n2,
                             agree=round(n2 / max(1, len(merged)), 3),
                             streams={k: len(v) for k, v in streams.items()},
                             secs=round(time.time() - t0, 1))
        print(f"[{i:2d}/{len(files)}] {name:9s} واژه={len(merged):4d} توافق≥۲: {n2:4d} "
              f"({n2/max(1,len(merged)):.0%})  {summary[name]['streams']} [{time.time()-t0:5.1f}s]",
              flush=True)
    json.dump(summary, open(f'{OUT}/_summary.json', 'w'), ensure_ascii=False, indent=1)
    tot = sum(v['n_words'] for v in summary.values())
    ag = sum(v['vote2plus'] for v in summary.values())
    print(f'\nمجموع واژه‌ها: {tot} | توافق ≥۲: {ag} ({ag/max(1,tot):.1%})')
    print('FA5_PIPELINE_DONE', flush=True)


if __name__ == '__main__':
    main()
