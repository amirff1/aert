#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fa_slide_prior — ساختِ گرامرِ هر قطعه از روی اسلایدهای همان قطعه
(«گوشِ زمینه‌آگاه»: واژگانِ مدل به اصطلاح‌های اسلایدِ در حال نمایش محدود می‌شود)"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, '/home/user/aert/voice-notes')
from fa_phonetic import TERMS, fa_key

DECK = Path('/home/user/aert/voice-notes/zadkamali/deck.json')
OUT = Path('/home/user/work/zadkamali/slide_prior_grammar.json')
BASE_FA = ['سینوسی', 'میترال', 'نرمال', 'آریتمی', 'ایسکمی', 'انفارکتوس', 'ولتاژ', 'موج', 'لید',
           'سگمنت', 'اینتروال', 'الکترود', 'استاندارد', 'محور', 'کیارس', 'اکسیس', 'دلتا', 'بلاک',
           'نود', 'ریتم', 'بزرگی', 'هایپرتروفی', 'پولمونر', 'اینفریور', 'آنتریور', 'لاترال',
           'سپتوم', 'پره‌کوردیال', 'همجوار', 'کالیبراسیون', 'گین', 'اسپید', 'اسکیل', 'فول',
           'میلی ولت', 'میلی متر', 'کیو تی', 'پی آر', 'اس تی', 'مانیتور', 'سیگنال']
BASE_EN = ['qrs', 'pr', 'st', 'qt', 'wpw', 'mi', 'axis', 'scale', 'gain', 'speed', 'delta',
           'segment', 'interval', 'sinus', 'rhythm', 'block', 'node', 'lead', 'leads', 'normal',
           'electrode', 'standard', 'calibration', 'millivolt', 'sokolow', 'ischemia', 'infarct',
           'arrhythmia', 'hypertrophy', 'pulmonary', 'inferior', 'anterior', 'lateral', 'septum',
           'precordial', 'contiguous', 'fragmented', 'bundle', 'branch', 'positive', 'negative',
           'paper', 'monitor', 'signal', 'v one', 'v two', 'v three', 'v four', 'v five', 'v six',
           'seven', 'eight', 'nine', 'augmented', 'amplified', 'full', 'standard']
MEDICAL_HINT = re.compile(r'(?i)\b(qrs|pr|st|qt|wpw|mi|lvh|rvh|bbb|lbbb|rbbb|ecg|ekg|axis|lead|'
                          r'ischemi|infarct|arrhythmi|hypertroph|block|fragment|sokolow|voltage|'
                          r'segment|interval|sinus|rhythm|delta|precordial|limb|chest|electrode|'
                          r'pulmonary|mitral|tricuspid|hyperkal|hypokal|depolar|repolar|isoelectric|'
                          r'bundle|fascicular|contiguous|transition|progression|positive|negative)\w*')


def main() -> None:
    deck = json.loads(DECK.read_text(encoding='utf-8'))
    per_clip_terms: dict[str, set[str]] = {}
    for sl in deck:
        txt = ' '.join(sl.get('text') or [])
        terms = set(m.group(0).lower() for m in MEDICAL_HINT.finditer(txt))
        for a in (sl.get('audio') or []):
            clip = a.split('.')[0]
            per_clip_terms.setdefault(clip, set()).update(terms)
    out = {}
    for clip, terms in per_clip_terms.items():
        terms = {t for t in terms if len(t) >= 3}
        if len(terms) >= 3:
            # اسلاید اصطلاح‌های اختصاصی دارد → گرامر فقط همان‌ها (رقابتِ کم، دقتِ زیاد)
            en = sorted(terms)
            fa = sorted({f for t in TERMS for f in t['fa'] if t['en'].lower() in terms})
            out[clip] = {'fa': sorted(set(fa) | {'موج', 'لید', 'سگمنت', 'ولتاژ', 'نرمال'}),
                         'en': en}
        else:
            out[clip] = {'fa': BASE_FA, 'en': BASE_EN}
        out[clip]['n_slide_terms'] = len(terms)
    for i in range(1, 32):
        c = f'media{i}'
        out.setdefault(c, {'fa': BASE_FA, 'en': BASE_EN})
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    n_slide_specific = sum(1 for c, g in out.items() if len(g['en']) < len(BASE_EN) + 5)
    print(f'✓ {OUT} — گرامرِ اختصاصی برای {len(out)} قطعه '
          f'(میانگین اصطلاح انگلیسی: {sum(len(g["en"]) for g in out.values())/len(out):.0f})')


if __name__ == '__main__':
    main()
