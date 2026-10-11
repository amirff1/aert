#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_pipeline2 — پیاده‌سازی فارسی با بالاترین دقتِ قابل‌دسترس
=========================================================
۱) نرمال‌سازی پیک صدا (کشف شد که صداها ~۵۰dB کم‌جان بودند)
۲) نویزگیری RNNoise (مدل عصبی، بدون نیاز به دانلود)
۳) اجرای **هر دو** مدل Vosk فارسی
۴) انتخاب خودکار مدل برنده در هر پنجرهٔ زمانی بر اساس اطمینان کلمات
خروجی: <out>/<media>.json  با segments و conf و مدل انتخابی
"""
import json, os, re, subprocess, sys, time, wave
import numpy as np, soundfile as sf
sys.path.insert(0, '/home/user/aert/voice-notes')
from rnnoise_dn import denoise_array
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)
FF = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
WORK = '/home/user/work/zadkamali'
OUT = f'{WORK}/fa2_out'
os.makedirs(OUT, exist_ok=True)
MODELS = {
    'fa042': '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42',
    'fa05':  '/home/user/asr-models/vosk-fa2',
}
WIN = 12.0          # پنجرهٔ انتخاب مدل (ثانیه)


def to_wav(src, dst):
    subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src,
                    '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst], check=True)


def prep(src, dst):
    """تبدیل + نرمال‌سازی پیک + نویزگیری RNNoise"""
    tmp = dst + '.tmp.wav'
    to_wav(src, tmp)
    x, sr = sf.read(tmp, dtype='float32')
    m = float(abs(x).max())
    if m > 1e-6:
        x = np.clip(x * (10 ** (-1.0 / 20) / m), -1, 1)
    sf.write(tmp, x, sr, subtype='PCM_16')
    xi, _ = sf.read(tmp, dtype='int16')
    try:
        y = denoise_array(xi, sr)
        sf.write(dst, y, sr, subtype='PCM_16')
    except Exception as e:
        print('   rnnoise warn:', e, file=sys.stderr)
        os.replace(tmp, dst)
        return
    os.remove(tmp)


def asr_segments(model, wav):
    wf = wave.open(wav, 'rb')
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    segs = []
    while True:
        b = wf.readframes(4000)
        if not b:
            break
        if rec.AcceptWaveform(b):
            r = json.loads(rec.Result())
            if r.get('text'):
                ws = r.get('result') or []
                segs.append(dict(t0=ws[0]['start'] if ws else 0.0,
                                 t1=ws[-1]['end'] if ws else 0.0,
                                 text=r['text'],
                                 conf=float(np.mean([w['conf'] for w in ws])) if ws else 0.0,
                                 words=ws))
    r = json.loads(rec.FinalResult())
    if r.get('text'):
        ws = r.get('result') or []
        segs.append(dict(t0=ws[0]['start'] if ws else 0.0,
                         t1=ws[-1]['end'] if ws else 0.0,
                         text=r['text'],
                         conf=float(np.mean([w['conf'] for w in ws])) if ws else 0.0,
                         words=ws))
    return segs


def pick_best(a, b):
    """انتخاب پنجره‌به‌پنجرهٔ مدل بهتر بر اساس اطمینان"""
    if not a and not b:
        return [], 'none'
    end = max([s['t1'] for s in a + b] or [0])
    out, wins = [], {'fa042': 0, 'fa05': 0}
    w = 0.0
    while w < end:
        wa = [s for s in a if s['t0'] < w + WIN and s['t1'] > w]
        wb = [s for s in b if s['t0'] < w + WIN and s['t1'] > w]
        ca = np.mean([s['conf'] for s in wa]) if wa else -1
        cb = np.mean([s['conf'] for s in wb]) if wb else -1
        src, tag = (wa, 'fa042') if ca >= cb else (wb, 'fa05')
        if wa and wb:
            wins[tag] += 1
        for s in src:
            if not any(o['text'] == s['text'] and abs(o['t0'] - s['t0']) < .01 for o in out):
                out.append(dict(s, model=tag))
        w += WIN
    out.sort(key=lambda s: s['t0'])
    return out, wins


def main():
    files = sorted([f for f in os.listdir(f'{WORK}/audio') if f.endswith('.m4a')],
                   key=lambda x: int(re.search(r'(\d+)', x).group(1)))
    loaded = {k: Model(p) for k, p in MODELS.items()}
    print('models loaded', flush=True)
    summary = {}
    for i, f in enumerate(files, 1):
        name = f[:-4]
        wav = f'{OUT}/{name}.wav'
        t0 = time.time()
        prep(f'{WORK}/audio/{f}', wav)
        res = {}
        for k, m in loaded.items():
            res[k] = asr_segments(m, wav)
        segs, wins = pick_best(res['fa042'], res['fa05'])
        text = ' '.join(s['text'] for s in segs)
        conf = float(np.mean([s['conf'] for s in segs])) if segs else 0.0
        json.dump({'media': name, 'text': text, 'conf': round(conf, 4),
                   'wins': wins, 'segments': segs},
                  open(f'{OUT}/{name}.json', 'w'), ensure_ascii=False, indent=1)
        open(f'{OUT}/{name}.txt', 'w').write(text + '\n')
        summary[name] = dict(conf=round(conf, 4), wins=wins, n=len(segs), secs=round(time.time() - t0, 1))
        print(f"[{i:2d}/{len(files)}] {name:10s} conf={conf:.3f} wins={wins} "
              f"chars={len(text):5d} [{time.time()-t0:5.1f}s]", flush=True)
        os.remove(wav)
    json.dump(summary, open(f'{OUT}/_summary.json', 'w'), ensure_ascii=False, indent=1)
    print('FA2_PIPELINE_DONE', flush=True)
    c = [v['conf'] for v in summary.values()]
    print(f'میانگین اطمینان: {np.mean(c):.4f}')


if __name__ == '__main__':
    main()
