#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_autotune — «تنظیم گوش» برای هر قطعه
=====================================
صدای درس با بهرهٔ خیلی کم ضبط شده (RMS حدود −۵۰ dBFS) و هرچه قطعه آرام‌تر،
دقت شنیدن پایین‌تر. این ابزار برای هر قطعه چند **زنجیرهٔ پیش‌پردازش** را
امتحان می‌کند و با یک معیارِ بی‌ناظر (توافق دو مدل + میانگین اطمینان) بهترین را
انتخاب می‌کند:

  ۱. resample ساده (شاهدِ پایه)
  ۲. loudnorm (بلندی هدف)
  ۳. speechnorm + dynaudnorm  (زنجیرهٔ فعلی)
  ۴. highpass + afftdn (کاهش نویز فرکانسی) + loudnorm
  ۵. compand (گسترش پایین‌رو + فشرده‌سازی رو‌به‌بالا) — سکوت را خفه، گفتار را بلند
  ۶. noisereduce (گیتینگ طیفی، پایتون) + loudnorm
  ۷. VTLN: تغییر گام/طول مجرای صوتی (+۵٪ و −۵٪)

خروجی: جدول امتیازها + best-chain.json (برای استفاده در اجرای بعدی رأی‌گیری)
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import soundfile as sf

FFMPEG = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
FA_A = '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42'
FA_B = '/home/user/asr-models/vosk-fa2'
AUDIO = Path('/home/user/work/zadkamali/audio')

CHAINS: list[tuple[str, str]] = [
    ('base16k', 'aresample=16000:resampler=soxr'),
    ('loudnorm', 'loudnorm=I=-18:TP=-1.5:LRA=11'),
    ('speechnorm_dyn', 'speechnorm=e=12.5:r=0.0001:l=1,dynaudnorm=f=200'),
    ('hp_afftdn_loud', 'highpass=f=80,afftdn=nr=18:nf=-45,loudnorm=I=-18:TP=-1.5'),
    ('compand_expand', "compand=attacks=0.02:decays=0.2:points=-80/-95|-45/-30|-20/-10|0/-3"),
    ('nr_gate', 'PY_NOISEREDUCE'),
    ('vtln_up', 'asetrate=16000*1.05,aresample=16000,atempo=0.95238,highpass=f=80'),
    ('vtln_down', 'asetrate=16000*0.95,aresample=16000,atempo=1.05263,highpass=f=80'),
]


def to_wav(clip: str, spec: str, out: Path) -> Path:
    if spec == 'PY_NOISEREDUCE':
        import noisereduce as nr
        tmp = out.with_name(out.stem + '_raw.wav')
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', str(AUDIO / f'{clip}.m4a'),
                        '-ar', '16000', '-ac', '1', str(tmp)], check=True)
        x, sr = sf.read(str(tmp), dtype='float32')
        y = nr.reduce_noise(y=x, sr=sr, stationary=False, prop_decrease=0.75,
                            n_fft=1024, win_length=512, time_mask_smooth_ms=120)
        y = y / (np.abs(y).max() + 1e-9) * 0.89          # نرمال‌سازی پیک
        sf.write(str(out), y, sr, subtype='PCM_16')
        tmp.unlink(missing_ok=True)
        return out
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', str(AUDIO / f'{clip}.m4a'),
                    '-ar', '16000', '-ac', '1', '-af', spec, '-f', 'wav', str(out)], check=True)
    return out


def decode(model, wav: Path, grammar=None) -> list[dict]:
    import json as _json, wave
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)
    if grammar:
        rec.SetGrammar(_json.dumps(grammar, ensure_ascii=False))
    words = []
    with wave.open(str(wav)) as wf:
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                words += _json.loads(rec.Result()).get('result', [])
    words += _json.loads(rec.FinalResult()).get('result', [])
    return words


def agree(a: list[dict], b: list[dict]) -> float:
    """شباهت واژه‌ای دو رشته (F1 واژه‌ای)"""
    wa = [w['word'] for w in a]
    wb = [w['word'] for w in b]
    if not wa or not wb:
        return 0.0
    sm = SequenceMatcher(None, wa, wb, autojunk=False)
    m = sum(bl.size for bl in sm.get_matching_blocks())
    return 2 * m / (len(wa) + len(wb))


def worker(args):
    clip, tmp = args
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    tmp = Path(tmp)
    ma, mb = Model(FA_A), Model(FA_B)
    res = {}
    for name, spec in CHAINS:
        w = tmp / f'{clip}_{name}.wav'
        try:
            to_wav(clip, spec, w)
        except Exception as e:                       # pragma: no cover
            res[name] = {'error': str(e)[:80]}
            continue
        a = decode(ma, w)
        b = decode(mb, w)
        conf = float(np.mean([x['conf'] for x in a])) if a else 0.0
        cf_b = float(np.mean([x['conf'] for x in b])) if b else 0.0
        lowa = sum(1 for x in a if x['conf'] < 0.6) / max(1, len(a))
        res[name] = {'words_a': len(a), 'words_b': len(b),
                     'conf_a': round(conf, 3), 'conf_b': round(cf_b, 3),
                     'agree': round(agree(a, b), 3), 'low_a': round(lowa, 3),
                     'score': round(0.5 * agree(a, b) + 0.25 * conf + 0.25 * cf_b, 4)}
        w.unlink(missing_ok=True)
        print(f'   {clip}/{name}: agree={res[name]["agree"]} conf={conf:.3f}/{cf_b:.3f}', flush=True)
    return clip, res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--clips', required=True, help='فهرست با کاما')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tmp', default='/tmp/autotune')
    ap.add_argument('--jobs', type=int, default=2)
    a = ap.parse_args()
    clips = [c.strip() for c in a.clips.split(',') if c.strip()]
    Path(a.tmp).mkdir(parents=True, exist_ok=True)

    out = {}
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for clip, res in ex.map(worker, [(c, a.tmp) for c in clips]):
            out[clip] = res
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    names = [n for n, _ in CHAINS]
    print('\n' + ' | '.join(f'{n[:14]:>14s}' for n in names))
    wins = {n: 0 for n in names}
    for clip, res in out.items():
        line = []
        best = max(((n, res[n].get('score', 0)) for n in names), key=lambda kv: kv[1])
        wins[best[0]] += 1
        for n in names:
            s = res[n].get('score')
            line.append(f'{"*" if n == best[0] else " "}{n[:9]:>9s}:{s if s is not None else 0:.3f}')
        print(f'{clip:8s} ' + ' | '.join(line))
    print('\nبرنده‌ها:', '، '.join(f'{k}({v})' for k, v in sorted(wins.items(), key=lambda kv: -kv[1]) if v))
    print(f'✓ {a.out}')


if __name__ == '__main__':
    main()
