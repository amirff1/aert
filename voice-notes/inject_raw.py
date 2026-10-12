#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_raw — جای‌گذاری «عین متن خام صدا» + لایهٔ شواهد در جزوه
=============================================================
سه لایه — همه با برچسبِ جدا، هیچ دستکاری‌ای در خودِ واژه‌ها:

  ۱) **متن خام** دقیقاً همان چیزی که رأی‌گیری شنیده؛ واژه‌های کم‌اطمینان داخل ‹›
  ۲) **پیشنهاد واژهٔ تخصصی** با ≈ — فقط اگر واژه شکلِ دقیقِ یک اصطلاح دامنه باشد
     یا تطبیق آوایی‌اش بی‌ابهام و واژه در پیکره کم‌بسامد باشد (دروازهٔ بسامد)
  ۳) **شاهدِ صوتی مستقل** با ✔ — رمزگشایی اجباری همان اصطلاح را در همان لحظه
     شنیده و متن آزاد هم تأیید کرده (ضریب ویژه‌بودن ۶٫۲× در آزمون جایگشتی)

خطِ سرآمدِ هر بلوک هم اصطلاح‌های شناسایی‌شدهٔ همان قطعه را با زمان می‌آورد.

اجرا (از پوشهٔ voice-notes):
    python inject_raw.py zadkamali/joze-kamel.md --transcript .../transcript-fa-final.json \
        --out zadkamali/joze-kamel.md --term-evidence .../termspot_validate.json
"""
from __future__ import annotations
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

MIN_VOTES = 2      # حداقل رأی برای «مطمئن»
MIN_CONF = 0.6     # حداقل اطمینان برای «مطمئن»

try:
    from fa_phonetic import Suggestor
    SUG = None            # با پیکره ساخته می‌شود
except Exception:         # pragma: no cover
    Suggestor = None       # type: ignore
    SUG = None

# نشانهٔ سرآمدِ بلوک خام (برای اجرای دوباره/به‌روزرسانی)
HDR = re.compile(r'(?m)^> 🔉 \*\*متن خام صدا — `(?P<name>media\d+)`\*\*')


def build_suggestor(corpus_words: list[str]):
    if Suggestor is None:
        return None
    return Suggestor(corpus_words)


def load_term_evidence(path: str | None) -> dict[str, list[dict]]:
    """{clip: [ {t, t_end, canon, evidence…} ]} از خروجی آزمون جایگشتی"""
    if not path or not Path(path).exists():
        return {}
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if not r.get('supported'):
            continue
        out[r['clip']].append({'t': r['t'], 't_end': r.get('t_end', r['t']),
                               'canon': r['canon'], 'heard': r['heard'],
                               'conf': r.get('conf'), 'ev': r.get('evidence')})
    for k in out:
        out[k].sort(key=lambda x: x['t'])
    return out


def term_line(clip: str, spots: list[dict]) -> str:
    """خطِ خلاصهٔ اصطلاح‌های شناسایی‌شدهٔ یک قطعه (حذف تکراری‌های نزدیک)"""
    if not spots:
        return ''
    picked: list[dict] = []
    for s in spots:
        if picked and s['t'] - picked[-1]['t'] < 1.5 and s['canon'] == picked[-1]['canon']:
            continue
        picked.append(s)
    items = []
    for s in picked[:14]:
        m, sec = divmod(s['t'], 60)
        items.append(f"{s['canon']} `{int(m):02d}:{sec:04.1f}`")
    more = f" … (+{len(picked)-14})" if len(picked) > 14 else ''
    return ('> 🎯 **اصطلاح‌های تخصصیِ شناسایی‌شده در همین قطعه** (دیکود اجباری + '
            'تأیید متن آزاد): ' + ' · '.join(items) + more)


def marked_clip(d: dict, name: str, spots: list[dict], sugg) -> tuple[str, dict]:
    """متن خام با ‹› روی واژه‌های کم‌اطمینان (+ ≈ پیشنهاد و ✔ شاهد صوتی)"""
    if name not in d:
        return f'⚠️ متن خام «{name}» یافت نشد.', {'n': 0, 'shaky': 0, 'sug': 0, 'wit': 0}
    ws = d[name]['words']
    parts, shaky, n_sug, n_wit = [], 0, 0, 0
    for w in ws:
        word = w['word']
        s, e = w['start'], w['end']
        conf_word = w['votes'] >= MIN_VOTES and w['conf'] >= MIN_CONF
        sug = sugg.suggest(word) if sugg else None
        # شاهد صوتی: اصطلاحی در همان بازه که معادلِ فارسی‌اش ≈ همین واژه باشد
        wit = None
        if sug:
            for sp in spots:
                if sp['t_end'] < s - 1.0 or sp['t'] > e + 1.0:
                    continue
                if sp['canon'].lower() == sug[0].lower() or _canon_eq(sp['canon'], sug[0]):
                    wit = sp
                    break
        tail = ''
        if sug:
            n_sug += 1
            tail = f' ≈ **{sug[0]}**'
        if wit:
            n_wit += 1
            tail += ' ✔'
        if conf_word and not tail:
            parts.append(word)
        elif conf_word:
            parts.append(f'{word}{tail}')
        else:
            shaky += 1
            alts = '، '.join(a['w'] for a in (w.get('alts') or [])[:2])
            parts.append(f"‹{word}{' / ' + alts if alts else ''}›{tail}")
    span = f"{ws[0]['start']:.0f}s → {ws[-1]['end']:.0f}s" if ws else '—'
    stats = {'n': len(ws), 'shaky': shaky, 'span': span, 'sug': n_sug, 'wit': n_wit,
             'pct': round(shaky / max(1, len(ws)) * 100)}
    return ' '.join(parts), stats


def _canon_eq(a: str, b: str) -> bool:
    from fa_phonetic import fa_key
    return bool(a) and fa_key(a) == fa_key(b)


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


def block_for(name: str, stats: dict, text: str, spots: list[dict]) -> str:
    bar = [f'> 🔉 **متن خام صدا — `{name}`**  ',
           f'> *(زمان {stats.get("span", "—")} · {stats.get("n", 0)} واژه · '
           f'{stats.get("shaky", 0)} واژهٔ کم‌اطمینان = {stats.get("pct", 0)}٪ · '
           f'{stats.get("sug", 0)} پیشنهاد واژه · {stats.get("wit", 0)} شاهد صوتی)*', '>']
    tl = term_line(name, spots)
    if tl:
        bar.append(tl)
        bar.append('>')
    for ln in wrap(text):
        bar.append('> ' + ln)
    return '\n'.join(bar)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('--transcript', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--term-evidence', default='')
    ap.add_argument('--gen', default='نسخهٔ صدا-اول')
    ap.add_argument('--standalone', action='store_true',
                    help='خروجی مستقل: متن خام همهٔ قطعه‌ها پشت سر هم')
    a = ap.parse_args()

    raw = json.loads(Path(a.transcript).read_text(encoding='utf-8'))
    corpus = [w['word'] for c in raw for w in raw[c].get('words', [])]
    sugg = build_suggestor(corpus)
    spots = load_term_evidence(a.term_evidence)
    print(f'لایه‌ها: پیشنهاد واژه {"فعال" if sugg else "غیرفعال"} · '
          f'شاهد صوتی: {sum(len(v) for v in spots.values())} اصطلاح در {len(spots)} قطعه')

    if a.standalone:
        out = ['# متن خام صدا — نسخهٔ نهایی (رأی‌گیری چندکانالی + شواهد)', '',
               '> واژه‌های داخل ‹کروشه› **کم‌اطمینان**اند؛ بعد از ‹/› یک یا دو گزینهٔ دیگر که',
               '> کانال‌های مستقل شنیده‌اند می‌آید. `≈ **X**` یعنی پیشنهاد واژهٔ تخصصی (بر پایهٔ',
               '> تطبیق آوایی با دروازهٔ کم‌بسامدی) و `✔` یعنی رمزگشایی اجباری هم در همان لحظه',
               '> همان اصطلاح را شنیده و متن آزاد تأییدش کرده. متن خام **هیچ دستکاری دیگری** نشده.', '']
        tot = sh = sn = wt = 0
        for i in range(1, 32):
            name = f'media{i}'
            t, st = marked_clip(raw, name, spots.get(name, []), sugg)
            tot += st.get('n', 0); sh += st.get('shaky', 0)
            sn += st.get('sug', 0); wt += st.get('wit', 0)
            out += [f'## {name} — {st.get("span", "—")} · {st.get("n", 0)} واژه · '
                    f'{st.get("shaky", 0)} کم‌اطمینان ({st.get("pct", 0)}٪)', '']
            tl = term_line(name, spots.get(name, []))
            if tl:
                out += [tl, '']
            out += [t, '']
        Path(a.out).write_text('\n'.join(out), encoding='utf-8')
        print(f'✓ متن خام مستقل نوشته شد → {a.out}')
        print(f'   مجموع {tot} واژه | کم‌اطمینان {sh} ({sh/max(1,tot):.1%}) | '
              f'پیشنهاد {sn} | شاهد صوتی {wt}')
        return

    md = Path(a.md).read_text(encoding='utf-8')
    report = [(m.group('name'), *marked_clip(raw, m.group('name'), spots.get(m.group('name'), []), sugg))
              for m in HDR.finditer(md)]
    have = {n for n, _, _ in report}
    total_n = total_shaky = total_sug = total_wit = 0
    out = md
    for name, text, stats in report:
        blk = block_for(name, stats, text, spots.get(name, []))
        pat = re.compile(rf'(?m)^> 🔉 \*\*متن خام صدا — `{name}`\*\*.*?'
                         rf'(?=^(?!>)|^> 🔉 \*\*متن خام صدا — )', re.S)
        if pat.search(out):
            out = pat.sub(lambda _m, b=blk: b, out, count=1)
        else:
            out = re.sub(rf'^<!--RAW:{name}-->$', lambda _m, b=blk: b, out, count=1, flags=re.M)
        total_n += stats.get('n', 0)
        total_shaky += stats.get('shaky', 0)
        total_sug += stats.get('sug', 0)
        total_wit += stats.get('wit', 0)

    # اگر بلوکی تازه اضافه شد؟ (نشانگر باقی‌مانده) — گزارش بده
    left = re.findall(r'^<!--RAW:(media\d+)-->$', out, re.M)
    Path(a.out).write_text(out, encoding='utf-8')
    print(f'✓ {len(report)} بلوک به‌روز شد → {a.out}' + (f' | نشانگر تزریق‌نشده: {left}' if left else ''))
    print(f'   مجموع واژه‌های خام: {total_n} | کم‌اطمینان: {total_shaky} '
          f'({total_shaky/max(1,total_n):.1%}) | پیشنهاد واژه: {total_sug} | شاهد صوتی: {total_wit}')
    if have != {f'media{i}' for i in range(1, 32)}:
        print('   ℹ️ قطعه‌های بدون بلوک در فایل:', sorted({f'media{i}' for i in range(1, 32)} - have,
                                                      key=lambda x: int(x[5:])))


if __name__ == '__main__':
    main()
