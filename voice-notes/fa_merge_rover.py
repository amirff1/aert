#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_merge_rover — رأی‌گیری نهایی روی «همهٔ کانال‌های مستقل» دو نسل
================================================================
کانال‌های fa4_out/streams (۶ جریان) و fa5_out/streams (۴ جریان) با هم ترکیب
می‌شوند (تا ۱۰ جریان مستقل: پیش‌پردازش‌های مختلف × دو مدل Vosk) و رأی‌گیری
واژه‌به‌واژه انجام می‌شود. نتیجه: مطمئن‌ترین متن خام برای جزوه.

خروجی: work/zadkamali/transcript-fa-final.json  (+ .md)
"""
from __future__ import annotations
import json, os, sys
import numpy as np
from pathlib import Path

sys.path.insert(0, '/home/user/aert/voice-notes')
from fa_pipeline5 import rover   # همان الگوریتم ROVER

W = Path('/home/user/work/zadkamali')
S1 = W / 'fa4_out' / 'streams'
S2 = W / 'fa5_out' / 'streams'
OUT = W / 'transcript-fa-final.json'


def main() -> None:
    result, rows = {}, []
    for i in range(1, 32):
        name = f'media{i}'
        streams: dict[str, list] = {}
        for tag, d in (('a', S1), ('b', S2)):
            p = d / f'{name}.json'
            if p.exists():
                for k, v in json.loads(p.read_text(encoding='utf-8')).items():
                    streams[f'{tag}:{k}'] = v
        # کانال پنجم: متن رأی‌گیری‌شدهٔ نسخهٔ قبلی (۶ جریانی) به‌عنوان رأی اضافی
        prev = W / 'transcript-fa-v3.json'
        if not prev.exists():
            prev = Path('/home/user/aert/voice-notes/zadkamali/transcript-fa-v3.json')
        if prev.exists():
            d = json.loads(prev.read_text(encoding='utf-8'))
            if name in d and d[name].get('words'):
                streams['prev:v3'] = d[name]['words']
        if not streams:
            continue
        merged = rover(streams)
        text = ' '.join(w['word'] for w in merged)
        n2 = sum(1 for w in merged if w['votes'] >= 2)
        n3 = sum(1 for w in merged if w['votes'] >= 3)
        result[name] = {'media': name, 'text': text, 'words': merged,
                        'stats': {'n_words': len(merged), 'vote2plus': n2, 'vote3plus': n3,
                                  'agree_ratio': round(n2 / max(1, len(merged)), 3),
                                  'streams': {k: len(v) for k, v in streams.items()}}}
        rows.append((name, len(merged), n2, n3, len(streams)))
        print(f'{name:9s} جریان={len(streams):2d} واژه={len(merged):4d} '
              f'توافق≥۲={n2:4d} ({n2/max(1,len(merged)):.0%}) توافق≥۳={n3:4d} '
              f'({n3/max(1,len(merged)):.0%})', flush=True)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    tot = sum(r[1] for r in rows)
    a2 = sum(r[2] for r in rows)
    a3 = sum(r[3] for r in rows)
    print(f'\nمجموع: {tot} واژه | توافق≥۲: {a2} ({a2/max(1,tot):.1%}) | '
          f'توافق≥۳: {a3} ({a3/max(1,tot):.1%})')
    print('MERGE_DONE', flush=True)


if __name__ == '__main__':
    main()
