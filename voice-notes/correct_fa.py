#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
correct_fa — پاک‌سازی متن پیاده‌شدهٔ فارسی با واژگان دامنه
=========================================================
۱) قواعد تصحیح خطاهای شناخته‌شدهٔ مدل (محور↔عکس، بردار↔باردار، QRS↔کیارس …)
۲) سنجش «معناداری» متن با wordfreq (فهرست واژگان فارسی)
۳) گزارش کامل هر تغییر برای بازبینی انسانی

استفاده:
    python3 correct_fa.py --in DIR --out DIR [--report FILE]
"""
from __future__ import annotations
import argparse, json, os, re
from pathlib import Path

# ------------------------------------------------------------------ قواعد
RULES: list[tuple[str, str, str]] = [
    # ---- اصطلاحات انگلیسی که مدل فارسی آن‌ها را خراب می‌کند
    (r'\b(?:کمپرسور\s+)?(?:شعار|کیارس|کوییز|کوپر|کی\s*آر\s*اس|آر\s*بی\s*بی\s*بی|آربی‌بی‌بی)\b',
     'QRS', 'کمپلکس QRS'),
    (r'\bآرای\s*ام\s*آی\b|\bآر\s*ای\s*ام\s*ای\b|\bآرام\s*آی\b|\bآر\s*امی\b',
     'MI', 'انفارکتوس میوکارد'),
    (r'\bاسکیل\b', 'scale', 'scale روی نوار'),
    (r'\bاسپید\b|\bاسپیده\b', 'speed', 'سرعت کاغذ'),
    (r'\bوای\s*فای\b|\bوی\s*اف\b', 'V1', 'لید V1'),
    # ---- واژه‌های فارسی که مدل به واژهٔ پرارتباط دیگری تبدیل کرده
    (r'\bعکس\b(?=[^\u0600-\u06FF]{0,6}(?:قلب|نرمال|درجه|محور|بین|های))', 'محور', 'axis'),
    (r'\bعکس‌های\b(?=\s*(?:قلب|نرمال))', 'محورهای', 'axis'),
    (r'\bرنج\s+نامه\b|\bرنجه\s+نامت?\b|\bرنجر\s+نرمال\b', 'رنج نرمال', 'normal range'),
    (r'منفی\s+سی\s+درجه', 'منفی ۳۰ درجه', '−۳۰°'),
    (r'\bباردار\b', 'بردار', 'vector'),
    (r'\bقدر\b(?=\s*(?:را|رو|به|از|و|$|،))', 'قلب', 'قلب'),
    (r'\bدکودا\b|\bپلاریزه\b|\bدی\s*پلاریزه\b', 'دپولاریزاسیون', 'depolarization'),
    (r'\bرپلاریزه\b', 'رپولاریزاسیون', 'repolarization'),
    (r'\bایزومتریک\b', 'ایزوالکتریک', 'isoelectric line'),
    (r'\bتاکتیکال\b', 'تاکی‌کاردی', 'tachycardia'),
    (r'\bولتااز\b|\bولتاژها\b', 'ولتاژ', 'voltage'),
    (r'\bتسبیح\b', 'تقسیم', 'تقسیم'),
    (r'\bسرد\s+می‌شن\b', 'ثبت می‌شن', 'ثبت'),
    (r'\bتحقیقات\b(?=\s*بزاره)', 'استاندارد', 'استاندارد'),
    (r'\bبرزیل\b', 'و همچنین', 'و همچنین'),
    (r'\bعروسی\b(?=\s+از)|\bعروسی\b', 'روشی', 'روشی'),
    (r'\bمان\s+اشاره\b|\bاعمال\s+اشاره\b', 'همان اشاره', 'همان اشاره'),
    (r'\bالکترون\b(?=\s*(?:ها|ها))', 'الکترود', 'electrode'),
    (r'\bالکترولیت\b', 'الکترود', 'electrode'),
    (r'\bسی\s*جی\b|\bسی‌جی\b(?=\s*حاصل)', 'ECG', 'ECG'),
    # ---- گین/سرعت (استاندارد ثبت) — بر اساس خطاهای واقعیِ متن نهایی
    (r'\bگنگ\b|\bگنت\b|\bگینگ\b', 'گین', 'gain'),
    (r'\bگریم\b', 'گین', 'gain (misheard)'),
    (r'میلی[\u200c]?متر\s+(?:ده|در|بر\s+ده)\s+ثانیه', 'میلی‌متر بر ثانیه', 'mm/s'),
    (r'\bمیلی\s*وات\b|\bمیلیون\s*وات\b', 'میلی‌ولت', 'mV'),
    (r'\bایده\s+(دو|یک|سه)\b', r'لید \1', 'Lead I/II/III'),
    (r'\bایده\s*دو\b', 'لید دو', 'Lead II'),
    (r'\bهیجی\s*راک\b|\bهیجیراک\b|\bهیپر\s*راک\b', 'هایپرتروفی', 'hypertrophy'),
    (r'\bاسکی\s+دو\b|\bاسکیل\s+دو\b', 'scale دو', 'scale'),
    (r'\bساعت\s+حرکت\b', 'سرعت حرکت', 'speed'),
    (r'\bتیکال\b|\bالکتریکال\b(?=\s*ی)', 'الکتریکال', 'electrical'),
    (r'\bپلاریزه\s+شان\b|\bپلاریزه\s+ایش\b|\bپلاریزه\s+ش\b', 'دپولاریزاسیون', 'depolarization'),
    # ---- پاک‌سازی‌های عمومی
    (r'\b(?:نه|آه|آقا|آره|بله|خب|دیگه|چیکار|چیزی|عزیز)\b(?=\s+\b(?:در|که|این|ما|به)\b)',
     '', 'پرکننده‌های گفتاری'),
    (r'\s{2,}', ' ', 'فاصله‌های اضافه'),
]


def apply_rules(text: str) -> tuple[str, list[dict]]:
    changes: list[dict] = []
    for pat, rep, why in RULES:
        new, n = re.subn(pat, rep, text)
        if n:
            changes.append({'pattern': pat, 'replacement': rep, 'why': why, 'count': n})
            text = new
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text, changes


def meaningfulness(text: str) -> dict:
    """نسبت واژه‌های موجود در فهرست فارسی و میانگین zipf"""
    try:
        from wordfreq import zipf_frequency, top_n_list
    except Exception:
        return {}
    known = set(top_n_list('fa', 60000))
    toks = [t for t in re.findall(r'[\u0600-\u06FF‌]{2,}', text)]
    if not toks:
        return {'n': 0, 'known_ratio': 0.0, 'zipf': 0.0}
    inlist = sum(1 for t in toks if t in known)
    z = sum(zipf_frequency(t, 'fa') for t in toks) / len(toks)
    return {'n': len(toks), 'known_ratio': round(inlist / len(toks), 3), 'zipf': round(z, 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description='پاک‌سازی متن فارسی ASR')
    ap.add_argument('--in', dest='indir', required=True)
    ap.add_argument('--out', dest='outdir', required=True)
    ap.add_argument('--report', default=None)
    args = ap.parse_args()

    ind, outd = Path(args.indir), Path(args.outdir)
    outd.mkdir(parents=True, exist_ok=True)
    report = {'files': []}
    agg_before, agg_after = [], []

    for p in sorted(ind.glob('media*.json')):
        d = json.loads(p.read_text(encoding='utf-8'))
        raw = d.get('text', '')
        clean, changes = apply_rules(raw)
        mb, ma = meaningfulness(raw), meaningfulness(clean)
        d['text_raw'] = raw
        d['text'] = clean
        # تصحیح در سطح قطعه‌ها هم اعمال شود
        for s in d.get('segments', []):
            s['text_raw'] = s.get('text', '')
            s['text'], _ = apply_rules(s['text_raw'])
        (outd / p.name).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
        (outd / (p.stem + '.txt')).write_text(clean + '\n', encoding='utf-8')
        report['files'].append({'media': d['media'], 'changes': changes,
                                'before': mb, 'after': ma,
                                'chars_before': len(raw), 'chars_after': len(clean)})
        agg_before.append(mb.get('known_ratio', 0))
        agg_after.append(ma.get('known_ratio', 0))
        print(f"{d['media']:10s} تغییر={sum(c['count'] for c in changes):3d} "
              f"واژه‌های شناخته‌شده: {mb.get('known_ratio',0):.3f} → {ma.get('known_ratio',0):.3f}")

    report['summary'] = {
        'files': len(report['files']),
        'total_changes': sum(c['count'] for f in report['files'] for c in f['changes']),
        'known_ratio_before': round(sum(agg_before) / max(1, len(agg_before)), 3),
        'known_ratio_after': round(sum(agg_after) / max(1, len(agg_after)), 3),
    }
    rp = Path(args.report) if args.report else (outd / '_correction_report.json')
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n✓ {report['summary']}\n  گزارش: {rp}")


if __name__ == '__main__':
    main()
