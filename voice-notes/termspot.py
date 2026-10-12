#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
termspot — نشان‌گذاری زمانی اصطلاح‌های تخصصی با «دیکود اجباری»
=============================================================
ایده: مدل زبانیِ باز روی گفتار فارسیِ پر از واژهٔ انگلیسی، «توهم» می‌زند؛
اما اگر واژگان مدل را به **فهرست اصطلاح‌های ECG** محدود کنیم (grammar/forced
decoding)، مدل مجبور می‌شود یا اصطلاح را بشنود یا `[unk]` بگوید.
نتیجه: هر بار که استاد واژهٔ تخصصی گفته، با زمان و اطمینان پیدا می‌شود.

هر پنجره (پیش‌فرض ۱٫۸ ثانیه، گام ۰٫۹) با دو مدل رمزگشایی می‌شود:
  • فارسی (کوچک ۰٫۴۲) با تلفظ‌های فارسی اصطلاح‌ها  («کیارس», «اسکیل» …)
  • انگلیسی (کوچک en-us) با شکل اصلی انگلیسی       («qrs», «axis» …)
و فقط شنیده‌های با اطمینان ≥ آستانه نگه داشته می‌شوند. `[unk]` یعنی «مطمئن
نیستم» — پس نرخ `[unk]` هم گزارش می‌شود (شاهدِ اینکه مدل همه‌جا اصطلاح نمی‌سازد).
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, wave
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fa_phonetic import TERMS  # noqa: E402

FFMPEG = '/home/user/asr-venv/lib/python3.11/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
FA_MODEL = '/home/user/asr-models/vosk-fa/vosk-model-small-fa-0.42'
EN_MODEL = '/home/user/asr-models/vosk-en/vosk-model-small-en-us-0.15'
CHAIN = 'speechnorm=e=12.5:r=0.0001:l=1,dynaudnorm=f=200'

EXTRA_EN = ['lead', 'leads', 'limb', 'chest', 'rhythm', 'atrial', 'ventricular', 'flutter',
            'fibrillation', 'strain', 'reciprocal', 'precordial', 'septal', 'posterior',
            'pacemaker', 'escape', 'junctional', 'epsilon', 'v one', 'v two', 'v three',
            'v four', 'v five', 'v six', 'one', 'two', 'three', 'four', 'five', 'six',
            'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'left', 'right', 'up',
            'down', 'full', 'standard', 'calibration', 'paper', 'deviation', 'progression',
            'transition', 'zone', 'fragmented', 'sokolow', 'reciprocal', 'evolving']
EXTRA_FA = ['سینوسی', 'میترال', 'پولمونر', 'هایپرتروفی', 'برادیکاردی', 'تاکی‌کاردی', 'تاکی کاردی',
            'آریتمی', 'ایسکمی', 'انفارکتوس', 'هیپرکالمی', 'هیپوکالمی', 'فاسیکولار', 'فرگمنتد',
            'سپتوم', 'پره‌کوردیال', 'اینفریور', 'آنتریور', 'لاترال', 'کانتیگیوس', 'سوکولو',
            'آمپلی‌تود', 'اینتروال', 'سگمنت', 'بلاک', 'مانیتور', 'الکترود', 'استاندارد',
            'کالیبراسیون', 'ریتم', 'سینوس', 'نود', 'دهلیزی', 'بطنی', 'پیس میکر', 'آرتیفکت',
            'دپولاریزاسیون', 'رپولاریزاسیون', 'ایزوالکتریک', 'ترنزیشن', 'پروگرشن', 'دلتا',
            'اپسیلون', 'موج', 'لید', 'لیدها', 'قلب', 'راست', 'چپ', 'بالا', 'پایین',
            'فول', 'استاندارد', 'تاخیر', 'انحراف', 'گذر', 'ناحیه', 'شمارش']


def term_lists() -> tuple[list[str], list[str]]:
    fa, en = list(EXTRA_FA), list(EXTRA_EN)
    for t in TERMS:
        en.append(t['en'])
        fa += t['fa']
    en = [x for x in dict.fromkeys(x.strip() for x in en) if x]
    fa = [x for x in dict.fromkeys(x.strip() for x in fa) if x]
    # چندواژه‌ای‌های انگلیسی با حرف‌خوانی هم امتحان می‌شوند
    en += ['q r s', 'p r', 's t', 'q t', 'b b b', 'l b b', 'r b b']
    return fa, en


def to_wav(audio: Path, clip: str, out: Path, chain: str = CHAIN) -> Path:
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', str(audio / f'{clip}.m4a'),
                    '-ar', '16000', '-ac', '1', '-af', chain or 'anull', '-f', 'wav', str(out)],
                   check=True)
    return out


def _decode(rec, data: bytes):
    if rec.AcceptWaveform(data):
        return json.loads(rec.Result()).get('result', [])
    return []


def worker(args):
    clip, fa_gram, en_gram, win, hop, min_conf, tmp, audio, chain = args
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    tmp = Path(tmp)
    raw = to_wav(Path(audio), clip, tmp / f'{clip}_16k.wav', chain)
    x, sr = sf.read(str(raw), dtype='int16')
    fa_m = Model(FA_MODEL)
    en_m = Model(EN_MODEL)

    def make(model, grammar):
        rec = KaldiRecognizer(model, sr)
        rec.SetWords(True)
        rec.SetGrammar(json.dumps(grammar, ensure_ascii=False))
        return rec

    occ, n_win, n_unk = [], 0, 0
    step = int(hop * sr)
    wlen = int(win * sr)
    for i in range(0, max(1, len(x) - wlen // 2), step):
        seg = x[i:i + wlen]
        if len(seg) < sr // 2:
            break
        data = seg.tobytes()
        n_win += 1
        for tag, model, gram in (('fa', fa_m, fa_gram), ('en', en_m, en_gram)):
            rec = make(model, gram)
            words = _decode(rec, data) + json.loads(rec.FinalResult()).get('result', [])
            unk = sum(1 for w in words if w['word'] == '[unk]')
            n_unk += unk
            for w in words:
                if w['word'] == '[unk]' or w.get('conf', 0) < min_conf:
                    continue
                occ.append({'clip': clip, 't': round(i / sr + w['start'], 2), 'term': w['word'],
                            'conf': round(w['conf'], 3), 'model': tag})
    return clip, occ, n_win, n_unk


def merge_occurrences(occ: list[dict], gap: float = 1.5) -> list[dict]:
    """شنیده‌های هم‌واژه در پنجره‌های هم‌پوشان را یکی می‌کند (بیشترین اطمینان)"""
    by_term: dict[str, list[dict]] = defaultdict(list)
    for o in occ:
        by_term[(o['term'], o['model'])].append(o)
    merged = []
    for (term, model), items in by_term.items():
        items.sort(key=lambda o: o['t'])
        cur = None
        for o in items:
            if cur and o['t'] - cur['t_end'] <= gap:
                cur['t_end'] = max(cur['t_end'], o['t'])
                if o['conf'] > cur['conf']:
                    cur['conf'], cur['t'] = o['conf'], o['t']
                cur['hits'] += 1
            else:
                if cur:
                    merged.append(cur)
                cur = {'clip': o['clip'], 'term': term, 'model': model, 't': o['t'],
                       't_end': o['t'], 'conf': o['conf'], 'hits': 1}
        if cur:
            merged.append(cur)
    return sorted(merged, key=lambda o: (o['clip'], o['t'], o['term']))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--clips', default='', help='فهرست با کاما؛ پیش‌فرض همه')
    ap.add_argument('--audio', default='/home/user/work/zadkamali/audio',
                    help='پوشهٔ صدا (پیش‌فرض: صدای اصلی؛ می‌توان پوشهٔ دنیویزشده داد)')
    ap.add_argument('--chain', default=CHAIN, help='زنجیرهٔ ffmpeg پیش از رمزگشایی')
    ap.add_argument('--grammar-json', default='',
                    help='گرامرِ مخصوصِ هر قطعه: {"mediaN": {"fa": [...], "en": [...]}}')
    ap.add_argument('--out-json', required=True)
    ap.add_argument('--out-md', required=True)
    ap.add_argument('--win', type=float, default=1.8)
    ap.add_argument('--hop', type=float, default=0.9)
    ap.add_argument('--min-conf', type=float, default=0.55)
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--tmp', default='/tmp/termspot')
    ap.add_argument('--min-hits', type=int, default=1, help='حداقل تعداد پنجرهٔ هم‌پوشان')
    a = ap.parse_args()

    fa_gram, en_gram = term_lists()
    fa_gram = fa_gram + ['[unk]']
    en_gram = en_gram + ['[unk]']
    clips = ([c.strip() for c in a.clips.split(',') if c.strip()] or
             [f'media{i}' for i in range(1, 32)])
    Path(a.tmp).mkdir(parents=True, exist_ok=True)
    perclip = {}
    if a.grammar_json and Path(a.grammar_json).exists():
        perclip = json.loads(Path(a.grammar_json).read_text(encoding='utf-8'))
    args = []
    for c in clips:
        g = perclip.get(c) or {}
        fg = (g.get('fa') or fa_gram) + ['[unk]']
        eg = (g.get('en') or en_gram) + ['[unk]']
        args.append((c, fg, eg, a.win, a.hop, a.min_conf, a.tmp, a.audio, a.chain))
    print(f'اسکن {len(clips)} قطعه · پنجره {a.win}s گام {a.hop}s · '
          f'{len(fa_gram)-1} اصطلاح فارسی، {len(en_gram)-1} انگلیسی', flush=True)

    all_occ, stats = [], {}
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for clip, occ, n_win, n_unk in ex.map(worker, args):
            all_occ += occ
            stats[clip] = {'windows': n_win, 'unk': n_unk, 'raw_hits': len(occ)}
            print(f'  ✓ {clip}: {len(occ)} شنیدهٔ اصطلاح در {n_win} پنجره '
                  f'({n_unk} پنجره/توکن unk)', flush=True)

    merged = merge_occurrences(all_occ)
    merged = [m for m in merged if m['hits'] >= a.min_hits]
    Path(a.out_json).write_text(json.dumps({'occurrences': merged, 'stats': stats},
                                           ensure_ascii=False, indent=1), encoding='utf-8')

    per_clip: dict[str, list[dict]] = defaultdict(list)
    for m in merged:
        per_clip[m['clip']].append(m)
    # فهرست یکتای اصطلاح‌ها
    gl: dict[str, dict] = {}
    for m in merged:
        g = gl.setdefault(m['term'], {'n': 0, 'clips': set(), 'best': 0})
        g['n'] += 1
        g['clips'].add(m['clip'])
        g['best'] = max(g['best'], m['conf'])

    md = ['# اصطلاح‌های تخصصیِ شنیده‌شده — با زمان و اطمینان', '',
          f'> روش: رمزگشایی **اجباری** (grammar) با دو مدل Vosk (فارسی ۰٫۴۲ و انگلیسی en-us)؛',
          f'> واژگان مدل به {len(fa_gram)-1} اصطلاح فارسی و {len(en_gram)-1} اصطلاح انگلیسی محدود شده است.',
          '> هر سطر یعنی «در این ثانیه از این قطعه، مدل با حذف گزینه‌های دیگر، این اصطلاح را شنید».',
          '> `hits` = چند پنجرهٔ هم‌پوشان آن را تأیید کرده‌اند.', '']
    tot_win = sum(s['windows'] for s in stats.values())
    tot_unk = sum(s['unk'] for s in stats.values())
    md += [f'- پنجره‌های اسکن‌شده: **{tot_win}** · شنیدهٔ اصطلاح: **{len(merged)}** · '
           f'ردِ صریح (`[unk]`): **{tot_unk}**', '']
    md += ['## واژه‌نامهٔ اصطلاح‌ها (به ترتیب بسامد)', '',
           '| اصطلاح | تعداد | قطعه‌ها | بهترین اطمینان |', '|---|---|---|---|']
    for term, g in sorted(gl.items(), key=lambda kv: -kv[1]['n']):
        cs = '، '.join(sorted(g['clips'], key=lambda c: int(re.sub(r'\D', '', c)))[:12])
        md.append(f"| **{term}** | {g['n']} | {cs} | {g['best']} |")
    md += ['', '## خطِ زمانِ هر قطعه', '']
    for clip in sorted(per_clip, key=lambda c: int(re.sub(r'\D', '', c))):
        md.append(f'### {clip}')
        md.append('')
        for m in per_clip[clip]:
            mm = int(m['t']) // 60
            ss = m['t'] % 60
            md.append(f"- `{mm:02d}:{ss:04.1f}` **{m['term']}** "
                      f"(مدل {m['model']} · اطمینان {m['conf']} · {m['hits']} پنجره)")
        md.append('')
    Path(a.out_md).write_text('\n'.join(md), encoding='utf-8')
    print(f'✓ {len(merged)} اصطلاح یکتا/تکرار در {len(per_clip)} قطعه → {a.out_json}')
    print(f'   واژه‌نامه: {len(gl)} اصطلاح متمایز')


if __name__ == '__main__':
    main()
