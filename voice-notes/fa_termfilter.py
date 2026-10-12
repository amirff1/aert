#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_termfilter — پالایش نهاییِ شنیده‌های اصطلاح
=============================================
خروجی آزمون جایگشتی را می‌گیرد و:

  ۱) تکه‌های حرف‌خوانی فارسیِ پشت‌سرهم را به سرواژه می‌چسباند («کی»+«آر»+«اس» → QRS)
  ۲) واژه‌های «عمومی/کوتاهِ فارسی» را که تصادفی هم شاهد می‌گیرند حذف می‌کند
     (مگر شاهد آن‌ها خودش کم‌بسامد باشد) — «چپ»، «بالا»، «قلب»، «ناحیه»، «ام»…
  ۳) شنیده‌های تکراریِ نزدیک را یکی می‌کند (برای نمایش)
خروجی: JSON پالایش‌شده + آمار
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fa_phonetic import fa_key, Suggestor  # noqa: E402

STOP = {'تود', 'کاردی', 'خیلی', 'کسی', 'الکتریک', 'چپ', 'راست', 'بالا', 'پایین', 'ناحیه',
        'قلب', 'شکلی', 'میشه', 'داریم', 'تو', 'دو', 'سه', 'یک', 'هفت', 'نه'}
GENERIC_FA = {'موج', 'ناحیه', 'بالا', 'پایین', 'راست', 'چپ', 'قلب', 'لید', 'لیدها', 'فول',
              'شمارش', 'گذر', 'انحراف', 'تاخیر', 'نود', 'ریتم', 'سینوس', 'نرمال', 'بلاک',
              'سیگنال', 'مانیتور', 'استاندارد', 'عکس', 'فاصله', 'همجوار', 'الکتریک', 'آریتمی'}
LETTERS_FA = {'کی', 'یو', 'آر', 'اس', 'تی', 'پی', 'ام', 'آی', 'بی', 'وی', 'دی', 'ال', 'ان',
              'دبلیو', 'سی', 'کیو', 'جی', 'اچ', 'زد', 'اف', 'آرای', 'آی', 'اِی'}
ACRO_READINGS = {
    'qrs': ['کی آر اس', 'کیو آر اس', 'کیارس', 'q r s'], 'pr': ['پی آر', 'پیر'],
    'st': ['اس تی', 'استی'], 'qt': ['کیو تی', 'کیوتی'], 'mi': ['ام آی', 'ام‌آی'],
    'wpw': ['دبلیو پی دبلیو', 'دبلیوپی‌دبلیو'], 'bbb': ['بی بی بی'],
}
DISPLAY = {'qrs': 'QRS', 'pr': 'PR', 'st': 'ST', 'qt': 'QT', 'mi': 'MI', 'wpw': 'WPW', 'bbb': 'BBB'}
READ2ACRO: list[tuple[str, str]] = []
for acro, readings in ACRO_READINGS.items():
    for r in readings:
        READ2ACRO.append((fa_key(r), acro))


def is_rare(word: str) -> bool:
    try:
        from wordfreq import zipf_frequency
        return zipf_frequency(word, 'fa') < 3.4
    except Exception:                                   # pragma: no cover
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', default='')
    a = ap.parse_args()

    rows = json.loads(Path(a.inp).read_text(encoding='utf-8'))
    rows = [r for r in rows if r.get('supported')]
    rows.sort(key=lambda r: (r['clip'], r['t']))

    # ۰) هر «شنیدهٔ خام» را با فرهنگ دامنه به اصطلاحِ استاندارد نگاشت می‌کنیم
    sugg = Suggestor([r['heard'] for r in rows])
    for r in rows:
        m = sugg.suggest(r['heard'])
        if m:
            r['canon'] = m[0]
            r['mapped_from'] = r['heard']

    # ۱) چسباندن حرف‌خوانی‌های پشت‌سرهم
    out, i, merged_n = [], 0, 0
    while i < len(rows):
        r = rows[i]
        if r['heard'] in LETTERS_FA and not r['heard'].isascii():
            chain = [r]
            j = i + 1
            while (j < len(rows) and rows[j]['clip'] == r['clip'] and rows[j]['heard'] in LETTERS_FA
                   and rows[j]['t'] - chain[-1]['t'] <= 0.9):
                chain.append(rows[j])
                j += 1
            joined = ''.join(c['heard'] for c in chain)
            k = fa_key(joined)
            acro = next((ac for key, ac in READ2ACRO if key == k), None)
            if acro:
                merged_n += 1
                out.append({**r, 'heard': joined, 'canon': DISPLAY[acro],
                            't_end': chain[-1].get('t_end', chain[-1]['t']),
                            'chain': [c['heard'] for c in chain]})
                i = j
                continue
            if len(chain) > 1:          # زنجیرهٔ بی‌معنا → دور ریخته می‌شود
                i = j
                continue
        i += 1
        out.append(dict(r))

    # ۲) حذف عمومی‌های فارسی
    kept, dropped = [], []
    for r in out:
        w = r['heard']
        ev = (r.get('evidence') or {}).get('w', '')
        if w in STOP or r['canon'] in STOP:
            dropped.append(r)
            continue
        if r.get('mapped_from') and r['canon'].isascii():
            kept.append(r)
            continue
        if (w in GENERIC_FA or w in LETTERS_FA) and not is_rare(ev) and not r.get('chain'):
            dropped.append(r)
            continue
        if r['canon'] in GENERIC_FA and not is_rare(ev):
            dropped.append(r)
            continue
        kept.append(r)

    # ۳) یکسان‌سازی نمایش
    for r in kept:
        c = r['canon'].lower()
        r['display'] = DISPLAY.get(c, r['canon'])
        if r['display'] == c and len(c) > 3:          # اصطلاح انگلیسی: حرف اول بزرگ
            r['display'] = c[0].upper() + c[1:]
    LABEL = {'میلی': 'میلی (mV)', 'ایزو': 'ایزو (isoelectric)', 'وات': 'وات (W)',
             'ولت': 'ولت (V)', 'اندامی': 'اندامی (limb)', 'فاصله': 'فاصله (interval)'}
    for r in kept:
        r['display'] = LABEL.get(r['display'], r['display'])

    Path(a.out).write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding='utf-8')

    per = {}
    for r in kept:
        per[r['display']] = per.get(r['display'], 0) + 1
    print(f'✓ ورودی {len(rows)} | پس از چسباندن حرف‌خوانی و پالایش: {len(kept)} '
          f'(حذف‌شده {len(dropped)} · سرواژه‌سازی {merged_n}) → {a.out}')
    print('   پرتکرار:', '، '.join(f'{k}({v})' for k, v in
                                sorted(per.items(), key=lambda kv: -kv[1])[:15]))
    if a.report:
        md = ['# اصطلاح‌های پالایش‌شده (نمایش)', '',
              f'- پیش از پالایش: {len(rows)} · پس از پالایش: **{len(kept)}** · '
              f'حذف‌شده به‌عنوان «عمومی/مبهم»: {len(dropped)}', '',
              '| قطعه | زمان | اصطلاح | شنیدهٔ خام | شاهد |', '|---|---|---|---|---|']
        for r in sorted(kept, key=lambda r: (int(re.sub(r'\D', '', r['clip'])), r['t'])):
            m, s = divmod(r['t'], 60)
            ev = r.get('evidence') or {}
            md.append(f"| {r['clip']} | `{int(m):02d}:{s:04.1f}` | **{r['display']}** | "
                      f"«{r['heard']}» | «{ev.get('w','—')}» |")
        md += ['', '## نمونه‌های حذف‌شده (نمونهٔ صادقانه)', '']
        for r in dropped[:40]:
            md.append(f"- {r['clip']} @{r['t']}s «{r['heard']}» → {r['canon']} "
                      f"(شاهد: «{(r.get('evidence') or {}).get('w','—')}»)")
        Path(a.report).write_text('\n'.join(md), encoding='utf-8')


if __name__ == '__main__':
    main()
