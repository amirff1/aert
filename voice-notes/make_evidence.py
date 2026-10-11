#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_evidence — ساخت «کارت شواهد» برای هر قطعهٔ صوتی
===================================================
هر کارت شامل: اسلاید(های) مربوطه + متن دقیق اسلاید + متن رأی‌گیری‌شده (نسل‌ها)
+ واژه‌های مشکوک (توافق کم یا اطمینان پایین) با گزینه‌های جایگزین.
خروجی: work/zadkamali/evidence/mediaN.md
"""
from __future__ import annotations
import json
from pathlib import Path

W = Path('/home/user/work/zadkamali')
OUT = W / 'evidence'
OUT.mkdir(exist_ok=True)


def main() -> None:
    deck = {s['slide']: s for s in json.loads((W / 'deck.json').read_text(encoding='utf-8'))}
    m2s = json.loads((W / 'media_to_slide.json').read_text(encoding='utf-8'))
    m2s = {k.split('.')[0]: int(v) for k, v in m2s.items()}
    # اسلایدهایی که چند قطعه دارند
    slide2media: dict[int, list[str]] = {}
    for m, s in m2s.items():
        slide2media.setdefault(s, []).append(m)

    v1 = {}
    for i in range(1, 32):
        p = W / 'fa_out' / f'media{i}.m4a.txt'
        v1[f'media{i}'] = p.read_text(encoding='utf-8').strip() if p.exists() else ''
    v2 = {}
    for i in range(1, 32):
        p = W / 'fa2_out' / f'media{i}.txt'
        v2[f'media{i}'] = p.read_text(encoding='utf-8').strip() if p.exists() else ''
    v3 = {m['media']: m for m in json.loads((W / 'transcript-fa-v2.json').read_text(encoding='utf-8')).values()}

    for i in range(1, 32):
        name = f'media{i}'
        sl = m2s.get(name)
        lines = [f'# {name} — اسلاید {sl}', '']
        if sl and sl in deck:
            st = deck[sl]
            lines += ['## متن دقیق اسلاید', '```']
            lines += [t for t in st['text'] if t.strip()]
            if st.get('notes'):
                lines += ['— notes —'] + st['notes']
            lines += ['```', '']
            sibs = [m for m in slide2media.get(sl, []) if m != name]
            if sibs:
                lines += [f'*این اسلاید قطعهٔ صوتی دیگری هم دارد: {", ".join(sibs)}*', '']
        d = v3.get(name)
        if d:
            lines += ['## متن رأی‌گیری‌شده (نسل ۳)', '',
                      '*توافقی:* ' + d['text_consensus'], '',
                      '*کامل:* ' + d['text'], '']
            susp = [w for w in d['words'] if w['votes'] == 1 and w['conf'] < 0.8]
            if susp:
                lines += ['## واژه‌های مشکوک (تک‌رأی، اطمینان کم) — با جایگزین‌ها', '',
                          '| زمان | برگزیده | رای | اطمینان | جایگزین‌ها |', '|---|---|---|---|---|']
                for w in susp:
                    alts = ' · '.join(f"{a['w']} ({a['v']}رأی/{a['c']})" for a in w['alts']) or '—'
                    lines += [f"| {w['start']} | {w['word']} | {w['votes']} | {w['conf']} | {alts} |"]
                lines += ['']
        lines += ['## نسل‌های قبلی (برای مقایسه)', '',
                  '*نسل ۱:* ' + v1.get(name, ''), '', '*نسل ۲:* ' + v2.get(name, ''), '']
        (OUT / f'{name}.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'✓ {len(list(OUT.glob("media*.md")))} کارت شواهد در {OUT} ساخته شد')


if __name__ == '__main__':
    main()
