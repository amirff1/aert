#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_raw — جای‌گذاری «عین متن خام صدا» داخل جزوه
=================================================
هر جا در فایل مارک‌داون خط `<!--RAW:mediaN-->` باشد، این اسکریپت آن را با متن
خامِ رَأی‌گیری‌شدهٔ همان قطعه جایگزین می‌کند — **بدون هیچ دستکاری در واژه‌ها**.
واژه‌های کم‌اطمینان با ‹کلمه / گزینه‌ها› علامت می‌خورند.

استفاده:
    python3 inject_raw.py joze-kamel.md --transcript transcript-fa-v5.json \
        --out joze-kamel-final.md
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

MIN_VOTES = 2      # حداقل رأی برای «مطمئن»
MIN_CONF = 0.6     # حداقل اطمینان برای «مطمئن»


def marked_clip(d: dict, name: str) -> tuple[str, dict]:
    """متن خام با علامت ‹› روی واژه‌های کم‌اطمینان"""
    if name not in d:
        return f'⚠️ متن خام «{name}» یافت نشد.', {'n': 0, 'shaky': 0}
    ws = d[name]['words']
    parts, shaky = [], 0
    for w in ws:
        if w['votes'] >= MIN_VOTES and w['conf'] >= MIN_CONF:
            parts.append(w['word'])
        else:
            shaky += 1
            alts = '، '.join(a['w'] for a in (w.get('alts') or [])[:2])
            parts.append(f"‹{w['word']}{' / ' + alts if alts else ''}›")
    span = f"{ws[0]['start']:.0f}s → {ws[-1]['end']:.0f}s" if ws else '—'
    stats = {'n': len(ws), 'shaky': shaky, 'span': span,
             'pct': round(shaky / max(1, len(ws)) * 100)}
    return ' '.join(parts), stats


def wrap(text: str, width: int = 88) -> list[str]:
    """شکستن متن به سطرهای کوتاه‌تر (برای زیبایی در PDF)"""
    words, lines, cur = text.split(' '), [], ''
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    if cur:
        lines.append(cur)
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('--transcript', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--gen', default='نسخهٔ صدا-اول')
    ap.add_argument('--standalone', action='store_true',
                    help='خروجی مستقل: متن خام همهٔ قطعه‌ها پشت سر هم')
    a = ap.parse_args()

    if a.standalone:
        raw = json.loads(Path(a.transcript).read_text(encoding='utf-8'))
        out = ['# متن خام صدا — نسخهٔ نهایی (رأی‌گیری چندکانالی)', '',
               '> واژه‌های داخل ‹کروشه› **کم‌اطمینان**اند؛ بعد از ‹/› یک یا دو گزینهٔ دیگر',
               '> که کانال‌های مستقل شنیده‌اند می‌آید. این متن **هیچ دستکاری دیگری** نشده است.', '']
        tot = sh = 0
        for i in range(1, 32):
            name = f'media{i}'
            t, st = marked_clip(raw, name)
            tot += st.get('n', 0); sh += st.get('shaky', 0)
            out += [f'## {name} — {st.get("span", "—")} · {st.get("n", 0)} واژه · '
                    f'{st.get("shaky", 0)} کم‌اطمینان ({st.get("pct", 0)}٪)', '', t, '']
        Path(a.out).write_text('\n'.join(out), encoding='utf-8')
        print(f'✓ متن خام مستقل نوشته شد → {a.out}')
        print(f'   مجموع {tot} واژه | کم‌اطمینان {sh} ({sh/max(1,tot):.1%})')
        return
    md = Path(a.md).read_text(encoding='utf-8')
    raw = json.loads(Path(a.transcript).read_text(encoding='utf-8'))
    if 'media1' not in raw and 'media1' in str(list(raw)[:3]):
        pass

    report = []
    for m in re.finditer(r'^<!--RAW:(media\d+)-->$', md, re.M):
        name = m.group(1)
        text, stats = marked_clip(raw, name)
        report.append((name, stats))
    # جای‌گذاری (از انتها به ابتدا تا اندیس‌ها جابه‌جا نشوند)
    out = md
    total_n = total_shaky = 0
    for name, stats in report:
        text, _ = marked_clip(raw, name)
        pct = stats.get('pct', 0)
        bar = [f'> 🔉 **متن خام صدا — `{name}`**  ',
               f'> *(زمان {stats.get("span", "—")} · {stats.get("n", 0)} واژه · '
               f'{stats.get("shaky", 0)} واژهٔ کم‌اطمینان = {pct}٪)*', '>']
        for ln in wrap(text):
            bar.append('> ' + ln)
        block = '\n'.join(bar)
        out = re.sub(rf'^<!--RAW:{name}-->$', lambda _m, b=block: b, out, count=1, flags=re.M)
        total_n += stats.get('n', 0)
        total_shaky += stats.get('shaky', 0)

    Path(a.out).write_text(out, encoding='utf-8')
    print(f'✓ {len(report)} قطعه تزریق شد → {a.out}')
    print(f'   مجموع واژه‌های خام: {total_n} | کم‌اطمینان: {total_shaky} '
          f'({total_shaky/max(1,total_n):.1%})')
    worst = sorted(report, key=lambda r: -r[1].get('pct', 0))[:5]
    print('   نامطمئن‌ترین قطعه‌ها:', ', '.join(f'{n} ({s.get("pct")}٪)' for n, s in worst))


if __name__ == '__main__':
    main()
