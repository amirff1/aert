#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
doc_patch_v6 — وصلهٔ متنیِ نسخهٔ «صدا-اول + شواهد» روی جزوه
==========================================================
کارهایی که می‌کند (همه بی‌خطر برای اجرای دوباره — اگر قبلاً انجام شده باشد،
دوباره کاری نمی‌کند):
  • دو نشان تازه (≈ و ✔) و 🎯 را به راهنمای نشان‌ها اضافه می‌کند
  • پاراگراف «حقیقتِ روش» را با نتایج روش‌های تازه به‌روز می‌کند
  • پیوند پیوست ث را در فهرست می‌گذارد
  • ردیف‌های تازه را به پیوست ت (شفافیت) اضافه می‌کند
"""
from __future__ import annotations
import sys
from pathlib import Path

GUIDE_ROW = "| ⏱ | زمان شروع قطعه در نوار ۳۲ دقیقه‌ای + شمارهٔ قطعه و اسلاید |"
GUIDE_NEW = """| ≈ **X** | **پیشنهاد واژهٔ تخصصی** برای واژه‌ای که ماشین کمی نامطمئن شنیده. این پیشنهاد *نیست* از صدا نیست — از دو چیز می‌آید: (الف) شکل دقیقِ واژه در واژگانِ تخصصی دامنه (مثل «سینوسی»)، (ب) تطبیق آواییِ بی‌ابهام که «دروازهٔ کم‌بسامدی» را رد کرده باشد (مثل «کیارس ≈ QRS»). خودِ واژهٔ خام سرِ جایش می‌ماند |
| ✔ | **شاهد صوتیِ مستقل:** رمزگشایی اجباری (واژگان محدود به اصطلاح‌ها) در همان لحظه همان اصطلاح را شنیده **و** متن آزاد نیز تأیید کرده است. اعتبارسنجی: ۲۲٫۵٪ در برابر ۳٫۶٪ِ تصادفی (۶٫۲۳×) |
| 🎯 | خطِ خلاصهٔ بالای بلوک صوتی: اصطلاح‌های تخصصیِ شناسایی‌شدهٔ همان قطعه با زمان دقیق |
| ⏱ | زمان شروع قطعه در نوار ۳۲ دقیقه‌ای + شمارهٔ قطعه و اسلاید |"""

TRUTH_OLD_START = "> **حقیقتِ روش:**"
TRUTH_NEW = """> **حقیقتِ روش:** هیچ مدل فارسیِ بهتری در این محیط قابل دریافت نبود؛ پس مسیر را از
> «مدلِ بزرگ‌تر» به «**شاهدِ بیشتر روی همان صدا**» عوض کردم و سه روش تازه افزودم:
> **(۱) رمزگشایی اجباری** با واژگانِ محدودشده به اصطلاح‌های ECG که واژه‌های انگلیسی
> (QRS، axis، gain، speed…) را از دلِ گفتارِ فارسی بیرون می‌کشد؛ **(۲) تطبیق آوایی** با
> دروازهٔ کم‌بسامدی برای پیشنهاد واژهٔ تخصصی؛ **(۳) بازبینی قانونیِ ۴۶۶ واژهٔ کم‌اطمینان**
> علیه همهٔ کانال‌های خام. رأی‌گیری روی ۱۰ کانال: **۹۲٫۲٪ واژه‌ها با ≥۲ رأی**،
> و **۱۲٫۹٪ واژه‌ها** همچنان کم‌اطمینان‌اند (‹› خورده‌اند). نتیجهٔ اصطلاح‌ها:
> **۲۱۲ شنیدهٔ تأییدشده با شاهدِ صوتیِ مستقل** (پیوست ث). متن خام کامل هر قطعه در
> `transcript-fa-v5.md` (خام) و `transcript-fa-v6-evidence.md` (خام + لایهٔ ≈ و ✔)
> و ابزارها در `voice-notes/` است. **برای استناد، فایل صوتی را بشنوید.**"""

TOC_OLD = "[پیوست پ: واژه‌نامه](#پ) · [پیوست ت: شفافیت](#ت)"
TOC_NEW = ("[پیوست پ: واژه‌نامه](#پ) · [پیوست ث: اصطلاح‌نامهٔ صوتی با زمان](#ث) · "
           "[پیوست ت: شفافیت](#ت)")

TRANS_ROW = "| موتور صدا | ۶ جریان، رأی‌گیری | + **۲ کانال تازه**: `speechnorm` و `dynaudnorm` |"
TRANS_NEW = """| موتور صدا | ۶ جریان، رأی‌گیری | **۱۰ کانال + رأی‌گیری** (دو کانال تازه: `speechnorm` و `dynaudnorm`) |
| اصطلاح‌های تخصصی | فقط در متن پنهان بود | **پیوست ث**: اصطلاح‌های تأییدشده با زمان و شاهد + خطِ زمان هر قطعه |
| واژه‌های نامطمئن | علامت‌دار ولی بی‌بازبینی | **بازبینی علیه همهٔ کانال‌ها** (`fa_lowconf_forensics.py`) |
| پیشنهاد واژهٔ تخصصی | نداشت | **≈ X** با دروازهٔ کم‌بسامدی (`fa_phonetic.py`) |
| راستی‌آزمایی روش | نداشت | **آزمون جایگشتی + گرامر کنترل** (`termspot_validate.py` / `termspot_audit.py`) |"""

REPRO_OLD = ("python3 voice-notes/inject_raw.py voice-notes/zadkamali/joze-kamel.md \\\n"
             ">     --transcript voice-notes/zadkamali/transcript-fa-v5.json \\\n"
             ">     --out voice-notes/zadkamali/joze-kamel.md")


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else 'zadkamali/joze-kamel.md')
    s = path.read_text(encoding='utf-8')
    n = 0

    if '≈ **X**' not in s and GUIDE_ROW in s:
        s = s.replace(GUIDE_ROW, GUIDE_NEW, 1); n += 1

    if '**۲۱۲ شنیدهٔ تأییدشده' not in s and TRUTH_OLD_START in s:
        head = s.index(TRUTH_OLD_START)
        end = s.index('\n', s.index('برای استناد، فایل صوتی را بشنوید.**', head))
        # تا انتهای همان پاراگراف بلوکی
        while end < len(s) and s[end + 1:end + 2] == '>':
            end = s.index('\n', end + 1)
        s = s[:head] + TRUTH_NEW + s[end:]; n += 1

    if 'پیوست ث' not in s.split('## فهرست')[1][:600] and TOC_OLD in s:
        s = s.replace(TOC_OLD, TOC_NEW, 1); n += 1

    if TRANS_ROW in s:
        s = s.replace(TRANS_ROW, TRANS_NEW, 1); n += 1

    if REPRO_OLD in s:
        s = s.replace(REPRO_OLD,
                      "python3 voice-notes/termspot.py --out-json … --out-md …      # رمزگشایی اجباری\n"
                      "> python3 voice-notes/fa_termfilter.py --in … --out …          # پالایش اصطلاح‌ها\n"
                      "> python3 voice-notes/inject_raw.py voice-notes/zadkamali/joze-kamel.md \\\n"
                      ">     --transcript voice-notes/zadkamali/transcript-fa-v5.json \\\n"
                      ">     --term-evidence …/termspot_final.json --out …/joze-kamel.md\n"
                      "> python3 voice-notes/fa_terms_doc.py --validate … --out … --inject-md …/joze-kamel.md", 1)
        n += 1

    path.write_text(s, encoding='utf-8')
    print(f'✓ {n} وصله اعمال شد → {path}')


if __name__ == '__main__':
    main()
