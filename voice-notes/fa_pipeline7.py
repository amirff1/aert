#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_pipeline7 — کانالِ «گیتینگِ طیفی» (noisereduce) برای همهٔ قطعه‌ها
==================================================================
چرا: صدا با بهرهٔ خیلی کم ضبط شده (RMS ≈ −۵۰ dBFS) و آزمونِ «تنظیم گوش» نشان داد
برای قطعه‌های آرام، کاهش نویزِ طیفی از هر زنجیرهٔ دیگری بهتر است
(`fa_autotune.py`: برندهٔ ۳ از ۶ قطعهٔ آرام؛ media29: توافق ۰٫۵۴ در برابر ۰٫۳۷).

این خط لوله برای **هر ۳۱ قطعه** یک کانال تازه می‌سازد:
    ffmpeg → 16k mono → noisereduce(prop_decrease=0.75) → نرمال‌سازی پیک → Vosk
با دو مدل فارسی (0.42 و 0.5) → دو جریان مستقل تازه برای رأی‌گیری.

خروجی: work/zadkamali/fa7_out/streams/mediaN.json  و  _summary.json
"""
from __future__ import annotations
import json, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

FFMPEG = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
WORK = Path('/home/user/work/zadkamali')
OUT = WORK / 'fa7_out'
MODELS = {'fa042': '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42',
          'fa05': '/home/user/asr-models/vosk-fa2'}


def denoise_wav(src: Path, dst: Path, prop: float = 0.75) -> Path:
    import noisereduce as nr
    raw = dst.with_name(dst.stem + '_raw.wav')
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', str(src), '-ar', '16000', '-ac', '1',
                    str(raw)], check=True)
    x, sr = sf.read(str(raw), dtype='float32')
    y = nr.reduce_noise(y=x, sr=sr, stationary=False, prop_decrease=prop,
                        n_fft=1024, win_length=512, time_mask_smooth_ms=120)
    peak = float(np.abs(y).max()) or 1.0
    sf.write(str(dst), (y / peak * 0.89).astype('float32'), sr, subtype='PCM_16')
    raw.unlink(missing_ok=True)
    return dst


def decode(model, wav: Path) -> list[dict]:
    import wave
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)
    words = []
    with wave.open(str(wav)) as wf:
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                words += json.loads(rec.Result()).get('result', [])
    words += json.loads(rec.FinalResult()).get('result', [])
    return words


def worker(name: str) -> tuple[str, dict, dict]:
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    tmp = Path('/tmp/fa7')
    tmp.mkdir(parents=True, exist_ok=True)
    wav = denoise_wav(WORK / 'audio' / f'{name}.m4a', tmp / f'{name}_nr.wav')
    out, stats = {}, {}
    for tag, path in MODELS.items():
        words = decode(Model(path), wav)
        out[f'nr_{tag}'] = words
        stats[f'nr_{tag}'] = {'n': len(words),
                              'conf': round(float(np.mean([w['conf'] for w in words])), 3) if words else 0,
                              'low': sum(1 for w in words if w['conf'] < 0.6)}
    wav.unlink(missing_ok=True)
    return name, out, stats


def main() -> None:
    jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    clips = [f'media{i}' for i in range(1, 32)]
    (OUT / 'streams').mkdir(parents=True, exist_ok=True)
    summary = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for name, out, stats in ex.map(worker, clips):
            (OUT / 'streams' / f'{name}.json').write_text(
                json.dumps(out, ensure_ascii=False), encoding='utf-8')
            summary[name] = stats
            print(f'  ✓ {name}: ' + ' · '.join(f"{k}: {v['n']} واژه (conf {v['conf']})"
                                               for k, v in stats.items()), flush=True)
    (OUT / '_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                       encoding='utf-8')
    tot = sum(v['n'] for s in summary.values() for v in s.values())
    print(f'FA7_PIPELINE_DONE در {time.time()-t0:.0f} ثانیه · مجموع {tot} واژه')


if __name__ == '__main__':
    main()
