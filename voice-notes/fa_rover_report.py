#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_rover_report — تولید متن نهاییِ رأی‌گیری‌شده + گزارش دقت
=========================================================
ورودی : work/zadkamali/fa3_out/*.json   (خروجی fa_pipeline3 — ROVER چهارجریانی)
خروجی : work/zadkamali/transcript-fa-v2.md / .json   (متن نهایی، پس از تصحیح دامنه)
         work/zadkamali/accuracy.json                  (معیارهای عددی همهٔ نسل‌ها)
"""
from __future__ import annotations
import json, os, re, statistics as st, sys
from pathlib import Path

sys.path.insert(0, '/home/user/aert/voice-notes')
from correct_fa import apply_rules

W = Path('/home/user/work/zadkamali')
FA3 = W / 'fa3_out'


def known_ratio(text: str, known: set) -> float:
    toks = re.findall(r'[\u0600-\u06FF‌]{2,}', text)
    return round(sum(1 for t in toks if t in known) / len(toks), 3) if toks else 0.0


def zipf_mean(text: str) -> float:
    from wordfreq import zipf_frequency
    toks = re.findall(r'[\u0600-\u06FF‌]{2,}', text)
    return round(sum(zipf_frequency(t, 'fa') for t in toks) / len(toks), 2) if toks else 0.0


def main() -> None:
    from wordfreq import top_n_list
    known = set(top_n_list('fa', 60000))
    slides = json.loads((W / 'slide_media_map.json').read_text(encoding='utf-8')) \
        if (W / 'slide_media_map.json').exists() else {}

    rows, out_json = [], {}
    for i in range(1, 32):
        name = f'media{i}'
        p3 = FA3 / f'{name}.json'
        if not p3.exists():
            continue
        d3 = json.loads(p3.read_text(encoding='utf-8'))
        raw = d3['text']
        # گونهٔ توافقی: واژه‌هایی که ≥۲ جریان روی آن‌ها توافق داشتند یا اطمینان بالا دارند
        cons_words = [w for w in d3['words'] if w['votes'] >= 2 or w['conf'] >= 0.75]
        cons_raw = ' '.join(w['word'] for w in cons_words)
        clean, changes = apply_rules(raw)
        clean_cons, _ = apply_rules(cons_raw)
        n_changes = sum(c['count'] for c in changes)

        # نسل‌های قبلی
        p2 = W / 'fa2_out' / f'{name}.txt'
        p1 = W / 'fa_out' / f'{name}.m4a.txt'
        t2 = p2.read_text(encoding='utf-8').strip() if p2.exists() else ''
        t1 = p1.read_text(encoding='utf-8').strip() if p1.exists() else ''

        rows.append({
            'media': name,
            'words_v1': len(re.findall(r'\S+', t1)),
            'words_v2': len(re.findall(r'\S+', t2)),
            'words_v3': d3['stats']['n_words'],
            'agree2': round(d3['stats']['vote2plus'] / max(1, d3['stats']['n_words']), 3),
            'kr_v1': known_ratio(t1, known), 'kr_v2': known_ratio(t2, known),
            'kr_v3': known_ratio(clean, known),
            'words_cons': len(cons_words),
            'kr_cons': known_ratio(clean_cons, known),
            'changes': n_changes,
            'slide': slides.get(name) or slides.get(f'{name}.m4a'),
        })
        out_json[name] = {'media': name, 'text_raw': raw, 'text': clean,
                          'text_consensus': clean_cons,
                          'words': d3['words'], 'stats': d3['stats'],
                          'corrections': changes, 'slide': rows[-1]['slide']}

    (W / 'transcript-fa-v2.json').write_text(json.dumps(out_json, ensure_ascii=False, indent=1),
                                             encoding='utf-8')

    # --- مارک‌داون خوانا (اسلاید به اسلاید)
    md = ['# پیاده‌سازی روایت استاد — نسخهٔ ۲ (رأی‌گیری چهارجریانی)', '',
          '> هر قطعه با **۴ جریان مستقل** پیاده شد (۲ پیش‌پردازش × ۲ مدل فارسی Vosk) و واژه‌ها',
          '> واژه‌به‌واژه با مهر زمانی هم‌تراز و با رأی اکثریت انتخاب شدند؛ سپس واژگان تخصصی تصحیح شد.',
          '> ستون «توافق» = سهم واژه‌هایی که حداقل ۲ جریان روی آن‌ها توافق داشتند.', '']
    n_words = sum(r['words_v3'] for r in rows)
    for r in rows:
        d = out_json[r['media']]
        md.append(f"## {r['media']}" + (f" — اسلاید {r['slide']}" if r['slide'] else ''))
        md.append(f"*{r['words_v3']} واژه · توافق ≥۲ جریان: {r['agree2']:.0%} · "
                  f"تصحیح واژگانی: {r['changes']} · واژه‌های توافقی: {r['words_cons']}*")
        md.append('')
        md.append(d['text_consensus'])
        md.append('')
    (W / 'transcript-fa-v2.md').write_text('\n'.join(md), encoding='utf-8')

    # --- معیارهای کلی
    acc = {
        'clips': len(rows),
        'words': {'v1_old_pipeline': sum(r['words_v1'] for r in rows),
                  'v2_dual_model': sum(r['words_v2'] for r in rows),
                  'v3_rover': sum(r['words_v3'] for r in rows)},
        'known_ratio': {'v1': round(st.mean(r['kr_v1'] for r in rows), 3),
                        'v2': round(st.mean(r['kr_v2'] for r in rows), 3),
                        'v3': round(st.mean(r['kr_v3'] for r in rows), 3),
                        'v3_consensus': round(st.mean(r['kr_cons'] for r in rows), 3)},
        'words_consensus': sum(r['words_cons'] for r in rows),
        'rover_agreement2plus': round(st.mean(r['agree2'] for r in rows), 3),
        'corrections_total': sum(r['changes'] for r in rows),
        'per_clip': rows,
    }
    (W / 'accuracy.json').write_text(json.dumps(acc, ensure_ascii=False, indent=1), encoding='utf-8')

    print(f"واژه‌ها: v1={acc['words']['v1_old_pipeline']}  "
          f"v2={acc['words']['v2_dual_model']}  v3(ROVER)={acc['words']['v3_rover']}")
    print(f"نرخ واژه‌های شناخته‌شده: v1={acc['known_ratio']['v1']}  "
          f"v2={acc['known_ratio']['v2']}  v3={acc['known_ratio']['v3']}  "
          f"v3-توافقی={acc['known_ratio']['v3_consensus']}")
    print(f"واژه‌های توافقی: {acc['words_consensus']} از {acc['words']['v3_rover']}")
    print(f"توافق ≥۲ جریان: {acc['rover_agreement2plus']:.1%} | تصحیح‌ها: {acc['corrections_total']}")
    print('✓ transcript-fa-v2.md/json و accuracy.json نوشته شد')


if __name__ == '__main__':
    main()
