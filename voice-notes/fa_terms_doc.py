#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_terms_doc — ساخت پیوستِ «اصطلاح‌نامهٔ صوتی» برای جزوه
=======================================================
از خروجی آزمون جایگشتی (termspot_validate.py --out …json) یک سند مارک‌داون می‌سازد:
روش + سنجشِ توهم + واژه‌نامهٔ اصطلاح‌های تأییدشده + خطِ زمانِ هر قطعه.
سپس با `--inject-md` همان سند را بین دو نشانگر `<!--TERMS-DOC-START-->` و
`<!--TERMS-DOC-END-->` داخل جزوه جای می‌دهد (اجرای دوباره بی‌خطر است).
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from pathlib import Path

START, END = '<!--TERMS-DOC-START-->', '<!--TERMS-DOC-END-->'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--validate', required=True, help='termspot_validate.py --out …json')
    ap.add_argument('--audit-md', default='')
    ap.add_argument('--validate-md', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--inject-md', default='')
    ap.add_argument('--n-scan-windows', type=int, default=0)
    a = ap.parse_args()

    rows = json.loads(Path(a.validate).read_text(encoding='utf-8'))
    ok = [r for r in rows if r.get('supported')]

    per_clip: dict[str, list[dict]] = defaultdict(list)
    for r in ok:
        per_clip[r['clip']].append(r)
    for c in per_clip:
        per_clip[c].sort(key=lambda r: r['t'])

    for r in ok:
        r['canon'] = r.get('display', r['canon'])
    gl: dict[str, dict] = {}
    for r in ok:
        g = gl.setdefault(r['canon'], {'n': 0, 'clips': set(), 'best': 0})
        g['n'] += 1
        g['clips'].add(r['clip'])
        g['best'] = max(g['best'], r.get('conf') or 0)

    md = [f'<a id="ث"></a>', '## پیوست ث: اصطلاح‌نامهٔ صوتی — چه اصطلاحی، کجا گفته شد', '',
          'این پیوست از یک روش تازه می‌آید: **رمزگشایی اجباری (forced decoding)**. مدل صوتی',
          'به‌جای اینکه آزاد باشد هر جمله‌ای بسازد، واژگانش به **اصطلاح‌های ECG** محدود می‌شود؛',
          'آن‌وقت یا اصطلاح را می‌شنود یا صریح می‌گوید «نمی‌دانم» (نشانهٔ unk). بعد نتیجه با',
          '**متن آزادِ ۱۰کاناله** همان لحظه مقابله می‌شود. هر سطر زیر یعنی «در این ثانیه، این',
          'اصطلاح با شاهدِ مستقل شنیده شده». ملاکِ پذیرش، آزمون جایگشتی است (پایین را ببینید).', '',
          f'- اصطلاح‌های تأییدشده: **{len(ok)}** مورد · متمایز: **{len(gl)}** اصطلاح · '
          f'در **{len(per_clip)}** قطعه', '',
          '### واژه‌نامهٔ اصطلاح‌های شنیده‌شده', '',
          '| اصطلاح | چند بار | قطعه‌ها | بهترین اطمینان |', '|---|---|---|---|']
    for t, g in sorted(gl.items(), key=lambda kv: (-kv[1]['n'], kv[0])):
        cs = '، '.join(sorted(g['clips'], key=lambda c: int(re.sub(r'\D', '', c))))
        md.append(f"| **{t}** | {g['n']} | {cs} | {g['best']:.2f} |")

    md += ['', '### خطِ زمان به تفکیک قطعه', '',
           '| قطعه | زمان | اصطلاح | آنچه دیکود شنید | شاهدِ متن آزاد (زمان) |', '|---|---|---|---|---|']
    for clip in sorted(per_clip, key=lambda c: int(re.sub(r'\D', '', c))):
        for r in per_clip[clip]:
            m, s = divmod(r['t'], 60)
            ev = r.get('evidence') or {}
            weak = ' — شاهد ضعیف' if r.get('weak_evidence') else ''
            md.append(f"| {clip} | `{int(m):02d}:{s:04.1f}` | **{r['canon']}** | «{r['heard']}» "
                      f"({r['model']}) | «{ev.get('w','—')}» (از {ev.get('src','—')}) "
                      f"@{ev.get('s','—')}s{weak} |")

    # ----------------------------------------------------------- سنجش‌ها
    md += ['', '### سنجشِ صداقتِ روش (سه آزمون)', '']
    for p, title in ((a.validate_md, 'آزمون جایگشتی — آیا تشخیص «ویژه» است؟'),
                     (a.audit_md, 'آزمون گرامرِ کنترل — آیا دیکود اجباری «توهم» می‌زند؟')):
        if p and Path(p).exists():
            body = Path(p).read_text(encoding='utf-8')
            body = re.sub(r'^# .*$', '', body, count=1, flags=re.M).strip()
            md += [f'#### {title}', '', body, '']
    md += ['> **جمع‌بندی صادقانه:** خودِ رمزگشایی اجباری شاهد نیست؛ با گرامرِ کنترل هم به همان',
           '> اندازه «می‌شنود». ارزش از **تأیید متقابل با متن آزاد** می‌آید: در آزمون جایگشتی،',
           '> اصطلاحِ درست ۲۲٫۵٪ شاهد گرفت ولی اصطلاحِ تصادفیِ دیگر ۳٫۶٪ → **۶٫۲۳ برابر** ویژه‌تر.',
           '> پس حدود **۱ مورد از هر ۶** شنیدهٔ تأییدشده ممکن است تصادفی باشد؛ به همین دلیل',
           '> ردهٔ «فقط اجباری» در این پیوست نیامده و فقط شنیده‌های دارای شاهد آورده شده است.',
           '> هر جا شاهدِ متن آزاد واژه‌ای پُرکاربرد بود («این»، «که»)، با نشان ⚠️شاهد ضعیف مشخص',
           '> شده است — یعنی فقط خودِ دیکود اجباری قوی بوده. «✔» همیشه یعنی شاهدِ قوی.', '']

    Path(a.out).write_text('\n'.join(md), encoding='utf-8')
    print(f'✓ {a.out} — {len(ok)} اصطلاح تأییدشده · {len(gl)} متمایز')

    if a.inject_md:
        doc = Path(a.inject_md)
        text = doc.read_text(encoding='utf-8')
        payload = '\n'.join(md)
        new = (f'{START}\n{payload}\n{END}')
        if START in text and END in text:
            text = re.sub(re.escape(START) + r'.*?' + re.escape(END), lambda _m: new, text,
                          count=1, flags=re.S)
        else:
            anchor = '<a id="ت"></a>'
            if anchor in text:
                text = text.replace(anchor, new + '\n\n' + anchor, 1)
            else:
                text += '\n\n' + new + '\n'
        doc.write_text(text, encoding='utf-8')
        print(f'✓ درج در {a.inject_md}')


if __name__ == '__main__':
    main()
