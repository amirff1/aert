#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""پیاده‌سازی دسته‌ای کل صداهای یک ارائه (Persian Vosk) + نقشهٔ اسلاید↔صدا."""
import json, glob, os, re, subprocess, sys, time, wave
sys.path.insert(0, '/home/user/aert/voice-notes')
import transcribe as T
from vosk import Model, KaldiRecognizer, SetLogLevel

WORK = '/home/user/work/zadkamali'
AUDIO = f'{WORK}/audio'
OUT = f'{WORK}/fa_out'
os.makedirs(OUT, exist_ok=True)
SetLogLevel(-1)

FF = T.find_ffmpeg()
print('loading model…', flush=True)
t0 = time.time()
MODEL = Model('/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42')
print(f'model ready in {time.time()-t0:.1f}s', flush=True)


def wav_of(src: str, dst: str) -> None:
    subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src,
                    '-af', 'afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11',
                    '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst], check=True)


def asr(wav: str) -> list[dict]:
    wf = wave.open(wav, 'rb')
    rec = KaldiRecognizer(MODEL, wf.getframerate())
    rec.SetWords(True)
    segs = []
    while True:
        d = wf.readframes(4000)
        if not d:
            break
        if rec.AcceptWaveform(d):
            r = json.loads(rec.Result())
            if r.get('text'):
                ws = r.get('result') or []
                segs.append({'t0': ws[0]['start'], 't1': ws[-1]['end'], 'text': r['text']})
    r = json.loads(rec.FinalResult())
    if r.get('text'):
        ws = r.get('result') or []
        segs.append({'t0': ws[0]['start'], 't1': ws[-1]['end'], 'text': r['text']})
    return segs


files = sorted(glob.glob(f'{AUDIO}/*.m4a'), key=lambda p: int(re.search(r'(\d+)', os.path.basename(p)).group(1)))
summary = {}
for i, f in enumerate(files, 1):
    name = os.path.basename(f)
    wav = f'{OUT}/{name}.wav'
    t0 = time.time()
    if not os.path.exists(wav):
        wav_of(f, wav)
    segs = asr(wav)
    os.remove(wav)
    txt = ' '.join(s['text'] for s in segs).strip()
    json.dump({'media': name, 'segments': segs, 'text': txt},
              open(f'{OUT}/{name}.json', 'w'), ensure_ascii=False, indent=1)
    open(f'{OUT}/{name}.txt', 'w').write(txt + '\n')
    summary[name] = {'chars': len(txt), 'segs': len(segs), 'secs': round(time.time() - t0, 1)}
    print(f"[{i:2d}/{len(files)}] {name:14s} {len(txt):5d} chars  {time.time()-t0:5.1f}s  | {txt[:70]}", flush=True)

json.dump(summary, open(f'{OUT}/_summary.json', 'w'), ensure_ascii=False, indent=1)
print('DONE_FA_ASR', flush=True)
