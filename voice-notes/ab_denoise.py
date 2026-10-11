#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""آزمایش A/B نویزگیری: کدام پیش‌پردازش، دقت Vosk را بیشتر می‌کند؟"""
import json, os, re, subprocess, sys, time, wave
import numpy as np, soundfile as sf
from vosk import Model, KaldiRecognizer, SetLogLevel
from pyrnnoise import RNNoise
import noisereduce as nr

SetLogLevel(-1)
FF = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
WORK = '/home/user/work/zadkamali'
OUT = os.path.join(WORK, 'ab')
os.makedirs(OUT, exist_ok=True)
MODEL = Model('/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42')

CLIPS = [2, 5, 8, 13, 20]          # ترکیبی از تمیز تا پرنویز
TERMS = ['قلب', 'الکترود', 'لید', 'موج', 'دهلیز', 'بطن', 'محور', 'فاصله', 'استاندارد',
         'سینوسی', 'ضربان', 'کمپلکس', 'سپتوم', 'دپولاریزاسیون', 'ایسکمی', 'آریتمی',
         'گره', 'راست', 'چپ', 'بالا', 'پایین', 'نوار', 'بیمار', 'طبیعی']


def ff(src, dst, af=None):
    cmd = [FF, '-hide_banner', '-loglevel', 'error', '-y', '-i', src]
    if af:
        cmd += ['-af', af]
    cmd += ['-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst]
    subprocess.run(cmd, check=True)


def rnnoise(src, dst):
    """RNNoise با pyrnnoise روی wav 16k"""
    d = RNNoise(sample_rate=16000)
    for _ in d.denoise_wav(src, dst):
        pass


def noisereduce_file(src, dst):
    x, sr = sf.read(src, dtype='float32')
    y = nr.reduce_noise(y=x, sr=sr, stationary=False, prop_decrease=0.85)
    sf.write(dst, y, sr, subtype='PCM_16')


def asr(wav):
    wf = wave.open(wav, 'rb')
    rec = KaldiRecognizer(MODEL, wf.getframerate())
    rec.SetWords(True)
    words, texts = [], []
    while True:
        b = wf.readframes(4000)
        if not b:
            break
        if rec.AcceptWaveform(b):
            r = json.loads(rec.Result())
            if r.get('text'):
                texts.append(r['text'])
            words += r.get('result') or []
    r = json.loads(rec.FinalResult())
    if r.get('text'):
        texts.append(r['text'])
    words += r.get('result') or []
    text = ' '.join(texts)
    conf = float(np.mean([w['conf'] for w in words])) if words else 0.0
    hits = sum(text.count(t) for t in TERMS)
    # سهم کلمات فارسی‌نویسه (نشانهٔ خروجی معنادار در برابر خرچنگ‌قورباغه)
    toks = text.split()
    persian = sum(1 for t in toks if re.fullmatch(r'[\u0600-\u06FF‌]+', t))
    return dict(text=text, n_words=len(toks), conf=round(conf, 3),
                term_hits=hits, persian_ratio=round(persian / max(1, len(toks)), 3))


def process(tag, src_m4a, n):
    wav = f'{OUT}/{n}_{tag}.wav'
    try:
        if tag == 'baseline':                 # همان چیزی که در جزوه استفاده شد
            ff(src_m4a, wav, 'afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11')
        elif tag == 'rnnoise':
            ff(src_m4a, wav)                  # فقط تبدیل فرمت
            rnnoise(wav, wav + ".dn.wav"); os.replace(wav + ".dn.wav", wav)
        elif tag == 'rnnoise_af':
            ff(src_m4a, wav)
            rnnoise(wav, wav + ".dn.wav")
            ff(wav + ".dn.wav", wav + ".af.wav", 'afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11')
            os.replace(wav + ".af.wav", wav)
        elif tag == 'nr_rnnoise':
            ff(src_m4a, wav)
            noisereduce_file(wav, wav + ".nr.wav")
            rnnoise(wav + ".nr.wav", wav + ".dn.wav")
            os.replace(wav + ".dn.wav", wav)
        st = asr(wav)
        os.remove(wav)
        return st
    except Exception as e:
        return dict(err=f'{type(e).__name__}: {e}')


def main():
    rows = {}
    tags = ['baseline', 'rnnoise', 'rnnoise_af', 'nr_rnnoise']
    for n in CLIPS:
        src = f'{WORK}/audio/media{n}.m4a'
        if not os.path.exists(src):
            continue
        rows[n] = {}
        for tag in tags:
            t0 = time.time()
            st = process(tag, src, n)
            st['secs'] = round(time.time() - t0, 1)
            rows[n][tag] = st
            print(f"  media{n:2d} {tag:12s} conf={st.get('conf','-')!s:>6s} "
                  f"words={st.get('n_words','-'):>4} terms={st.get('term_hits','-'):>3} "
                  f"persian={st.get('persian_ratio','-')} [{st['secs']}s]", flush=True)
    json.dump(rows, open(f'{OUT}/ab_results.json', 'w'), ensure_ascii=False, indent=1)
    print('\n=== میانگین اطمینان (بالاتر = بهتر) ===')
    for tag in tags:
        vals = [rows[n][tag].get('conf', 0) for n in rows]
        print(f'  {tag:12s} {np.mean(vals):.3f}')
    print('=== میانگین اصطلاحات ECG ===')
    for tag in tags:
        vals = [rows[n][tag].get('term_hits', 0) for n in rows]
        print(f'  {tag:12s} {np.mean(vals):.1f}')


if __name__ == '__main__':
    main()
