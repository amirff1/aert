#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_slide_imgs — استخراج تصاویر هر اسلاید از فایل pptx
=========================================================
برای هر اسلاید، تصاویر جاسازی‌شدهٔ بزرگ (شکل‌ها/نمودارها/نوارهای قلب) را از
مسیر `ppt/media/` بیرون می‌کشد و نام‌گذاری می‌کند: `s<شمارهٔ اسلاید>_<نام اصلی>`.

نکته: در این محیط `raw.githubusercontent` و دانلود LFS مسدود است ولی خواندن
خودِ pptx با zipfile کار می‌کند.

استفاده:
    python3 extract_slide_imgs.py "دکتر زادکمالی.pptx" --out work/zadkamali/slide_imgs
    # گزینه‌ها: --min-kb 40 (حداقل حجم) --max-px 1400 (کوچک‌سازی) --jpeg-quality 85
"""
from __future__ import annotations
import argparse
import io
import os
import re
import zipfile
from pathlib import Path

IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('pptx')
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-kb', type=float, default=40, help='تصاویر کوچک‌تر از این حجم رد شوند (آیکون‌ها)')
    ap.add_argument('--max-px', type=int, default=1400, help='حداکثر بُعد تصویر خروجی (کوچک‌سازی)')
    ap.add_argument('--jpeg-quality', type=int, default=85)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(args.pptx)

    rels = {n: z.read(n).decode('utf-8', 'ignore')
            for n in z.namelist()
            if re.match(r'ppt/slides/_rels/slide\d+\.xml\.rels$', n)}

    def slide_no(n: str) -> int:
        return int(re.search(r'slide(\d+)\.xml', n).group(1))

    from PIL import Image
    seen: dict[str, str] = {}       # محتوای یکسان → فقط یک بار ذخیره شود
    rows = []
    for n, body in sorted(rels.items(), key=lambda kv: slide_no(kv[0])):
        s = slide_no(n)
        for name in re.findall(r'Target="\.\./media/([^"]+)"', body):
            if not name.lower().endswith(IMG_EXT):
                continue
            try:
                data = z.read('ppt/media/' + name)
            except KeyError:
                continue
            if len(data) < args.min_kb * 1024:
                continue
            im = Image.open(io.BytesIO(data))
            if im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            w, h = im.size
            if max(w, h) > args.max_px:
                k = args.max_px / max(w, h)
                im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
            stem = f's{s:02d}_{Path(name).stem}'
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=args.jpeg_quality, optimize=True)
            blob = buf.getvalue()
            key = f'{im.size}'
            if key in seen:          # تصویر تکراری (مثل s21/s34) دوباره ذخیره نشود
                rows.append((s, name, seen[key], len(blob), True))
                continue
            dst = out / f'{stem}.jpg'
            dst.write_bytes(blob)
            seen[key] = dst.name
            rows.append((s, name, dst.name, len(blob), False))

    total = sum(r[3] for r in rows if not r[4])
    print(f'{"اسلاید":>7s}  {"نام اصلی":22s} {"خروجی":26s} {"حجم":>8s}  تکراری')
    for s, name, dst, sz, dup in rows:
        print(f'{s:7d}  {name:22s} {dst:26s} {sz/1024:7.0f}K  {"✓" if dup else ""}')
    print(f'\n✓ {sum(1 for r in rows if not r[4])} تصویر ذخیره شد، '
          f'{sum(1 for r in rows if r[4])} تکراری رد شد — مجموع {total/1e6:.1f} MB در {out}')


if __name__ == '__main__':
    main()
