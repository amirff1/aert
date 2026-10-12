#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2pdf — تبدیل مارک‌داون فارسی به PDF راست‌به‌چپ و آمادهٔ چاپ
==========================================================
بدون نیاز به مرورگر/کروم: با fpdf2 + موتور شکل‌دهی HarfBuzz و فونت وزیرمتن.
پشتیبانی: سرتیترها، پاراگراف، نقل‌قول (نوار رنگی)، جدول RTL، لیست، بلوک کد،
پررنگ، خط افقی، سرصفحه/پاصفحه، و فهرست راهنمای PDF (bookmark).

استفاده:
    python3 md2pdf.py joze-kamel.md --out joze-kamel.pdf --title "جزوهٔ کامل ECG"
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

FONT_DIR = Path(__file__).resolve().parent / 'fonts'
INK = (31, 41, 51)
MUTED = (82, 96, 109)
ACCENT = (15, 118, 110)      # سبزآبی
ACCENT2 = (180, 83, 9)       # نارنجی
BG_QUOTE = (250, 248, 242)
BG_CODE = (244, 246, 248)
LINE = (228, 231, 235)

# نشان‌هایی که فونت وزیرمتن ندارد → معادل متنی
EMOJI_MAP = {
    '🎙': '', '📊': '', '📌': '', '💡': 'نکته:', '⚠️': 'توجه:', '⚠': 'توجه:',
    '🫀': '', '🏆': '', '🔎': '', '🔑': '', '✅': '', '✓': '', '●': '•',
    '🟢': ' [اطمینان: بالا]', '🟡': ' [اطمینان: متوسط]', '🔴': ' [اطمینان: کم]',
    '⏱': 'زمان:', '→': '>', '←': '<', '↑': '^', '↓': 'v', '⇒': '=>',
    '🙂': '', '😊': '', '✨': '', '🔥': '', '📄': '', '📁': '', '🚀': '',
}
ARROW_RE = re.compile('|'.join(re.escape(k) for k in sorted(EMOJI_MAP, key=len, reverse=True)))


def clean(text: str) -> str:
    """جایگزینی نشان‌های بدون گلیف + حذف مارک‌داونِ درون‌خطی ناسازگار"""
    text = re.sub(r'<a id="[^"]*">\s*</a>', '', text)      # لنگرهای HTML
    text = re.sub(r'<a id="[^"]*">', '', text)
    text = text.replace('</a>', '')
    text = ARROW_RE.sub(lambda m: EMOJI_MAP[m.group(0)], text)
    text = text.replace('**', '')          # پررنگِ داخل سلول جدول را ساده می‌کنیم
    text = text.replace('<br>', ' / ').replace('<', '‹').replace('>', '›')
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)          # حذف پیوندها
    return text


class JozePDF(FPDF):
    def __init__(self, title: str, subtitle: str = '', img_root: Path | None = None):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.doc_title, self.doc_sub = title, subtitle
        self.img_root = img_root or Path.cwd()
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, margin=18)
        self.add_font('Vazir', '', str(FONT_DIR / 'Vazirmatn-Regular.ttf'))
        self.add_font('Vazir', 'B', str(FONT_DIR / 'Vazirmatn-Bold.ttf'))
        self.set_text_shaping(True)
        self.lh = 6.6

    # ---------------------------------------------------------------- سرصفحه/پاصفحه
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('Vazir', '', 8)
        self.set_text_color(*MUTED)
        self.set_y(9)
        self.cell(0, 5, self.doc_title, align='R')
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(16, 14, self.w - 16, 14)
        self.set_y(17)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-12)
        self.set_font('Vazir', '', 8)
        self.set_text_color(*MUTED)
        self.set_draw_color(*LINE)
        self.line(16, self.h - 15, self.w - 16, self.h - 15)
        self.cell(0, 6, f'صفحهٔ {self.page_no() - 1}', align='L')

    # ---------------------------------------------------------------- عناصر
    def h1(self, text: str):
        self.set_font('Vazir', 'B', 20)
        self.set_text_color(*ACCENT)
        self.multi_cell(0, 11, clean(text), align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*ACCENT)
        self.set_line_width(0.8)
        y = self.get_y() + 1
        self.line(16, y, self.w - 16, y)
        self.ln(4)

    def h2(self, text: str):
        self.ln(3)
        if self.get_y() > self.h - 40:
            self.add_page()
        self.set_font('Vazir', 'B', 14.5)
        self.set_text_color(*ACCENT)
        self.multi_cell(0, 9, clean(text), align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        y = self.get_y() + 0.8
        self.line(16, y, self.w - 16, y)
        self.ln(3)

    def h3(self, text: str):
        self.set_font('Vazir', 'B', 12)
        self.set_text_color(19, 78, 74)
        self.multi_cell(0, 8, clean(text), align='R', new_x='LMARGIN', new_y='NEXT')
        self.ln(1)

    def para(self, text: str, bold: bool = False, size: float = 10.5,
             indent: float = 0, color=None, right_bar: tuple | None = None):
        self.set_font('Vazir', 'B' if bold else '', size)
        self.set_text_color(*(color or INK))
        x_left = self.l_margin + indent
        w = self.w - self.l_margin - self.r_margin - indent
        y0 = self.get_y()
        self.set_x(self.l_margin)
        # پاراگراف راست‌چین با عرض کم‌شده
        self.multi_cell(w, self.lh, clean(text), align='R', new_x='LMARGIN', new_y='NEXT')
        if right_bar:
            self.set_fill_color(*right_bar)
            self.rect(self.w - self.r_margin - 1.6, y0, 1.6, self.get_y() - y0 - 1.2, 'F')
        self.ln(1.5)

    def quote(self, lines: list[str]):
        y0 = self.get_y()
        x0 = self.l_margin
        w = self.w - self.l_margin - self.r_margin
        self.set_x(x0)
        for ln in lines:
            size, bold, color = 10.5, False, (54, 66, 78)
            if ln.startswith('> 🎙') or ln.startswith('> 📊') or ln.startswith('> 📌') \
               or ln.startswith('> 💡') or ln.startswith('> ⚠'):
                bold = True
            elif ln.startswith('>'):
                size = 10.5
            self.set_font('Vazir', 'B' if bold else '', size)
            self.set_text_color(*(ACCENT if bold else color))
            self.set_x(x0)
            self.multi_cell(w - 6, self.lh, clean(ln[2:].strip()), align='R',
                            new_x='LMARGIN', new_y='NEXT')
        y1 = self.get_y()
        self.set_fill_color(*BG_QUOTE)
        self.rect(x0 + w - 1.8, y0, 1.8, y1 - y0, 'F')
        self.ln(2)

    def code_block(self, lines: list[str]):
        self.set_font('Vazir', '', 9)
        self.set_text_color(40, 50, 60)
        h = self.lh * 0.92
        y0 = self.get_y()
        self.set_fill_color(*BG_CODE)
        self.rect(self.l_margin, y0, self.w - self.l_margin - self.r_margin, h * len(lines) + 3, 'F')
        self.ln(1.5)
        for ln in lines:
            self.set_x(self.l_margin + 2)
            self.multi_cell(self.w - self.l_margin - self.r_margin - 4, h, ln or ' ', align='L',
                            new_x='LMARGIN', new_y='NEXT')
        self.ln(2.5)

    def table_block(self, rows: list[list[str]]):
        header, body = rows[0], rows[1:]
        n = len(header)
        avail = self.w - self.l_margin - self.r_margin
        # عرض ستون‌ها: ستون اول کمی باریک‌تر
        weights = [1.0] + [1.7] * (n - 1) if n > 1 else [1.0]
        widths = [avail * w / sum(weights) for w in weights]
        # چیدمان راست‌به‌چپ: ترتیب ستون‌ها برعکس
        hdr = list(reversed([clean(c) for c in header]))
        body = [list(reversed([clean(c) for c in r])) for r in body]
        self.set_draw_color(*LINE)
        self.set_font('Vazir', '', 9.5)
        with self.table(col_widths=tuple(widths), text_align='RIGHT', line_height=6.2,
                        first_row_as_headings=True, borders_layout='ALL', padding=(1.6, 1.2, 1.6, 1.2),
                        headings_style=FontFace(emphasis='BOLD', color=(255, 255, 255),
                                                fill_color=ACCENT),
                        cell_fill_color=(247, 250, 252), cell_fill_mode='ROWS') as t:
            row = t.row()
            for c in hdr:
                row.cell(c)
            for r in body:
                row = t.row()
                for c in r:
                    row.cell(c)
        self.ln(2.5)

    def image_block(self, rel: str, caption: str = ''):
        """تصویر اسلاید: متناسب با عرض صفحه، با کپشن فارسی"""
        from PIL import Image as PILImage
        path = (self.img_root / rel) if not Path(rel).is_absolute() else Path(rel)
        if not path.exists():
            self.para(f'[تصویر یافت نشد: {rel}]', size=9, color=MUTED)
            return
        avail = self.w - self.l_margin - self.r_margin
        with PILImage.open(path) as im:
            nw, nh = im.size
        w, h = avail, avail * nh / nw
        if h > 148:                       # بلندتر از حد مجاز → با ارتفاع محدود کن
            h = 148
            w = h * nw / nh
        need = h + (7 if caption else 2) + 5
        if self.get_y() + need > self.h - self.b_margin:
            self.add_page()
        x = self.l_margin + (avail - w) / 2
        y = self.get_y()
        self.set_draw_color(*LINE)
        self.set_line_width(0.25)
        self.rect(x - 0.6, y - 0.6, w + 1.2, h + 1.2)
        self.image(str(path), x=x, y=y, w=w, h=h)
        self.set_y(y + h + 1.8)
        if caption:
            self.set_font('Vazir', '', 8.8)
            self.set_text_color(*MUTED)
            self.set_x(self.l_margin)
            self.multi_cell(avail, 5.4, clean(caption), align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def hr(self):
        self.ln(1)
        self.set_draw_color(*LINE)
        self.set_line_width(0.3)
        self.line(16, self.get_y(), self.w - 16, self.get_y())
        self.ln(3)

    def bullet(self, text: str, ordered: str = ''):
        self.set_font('Vazir', '', 10.5)
        self.set_text_color(*INK)
        mark = ordered if ordered else '•'
        self.set_x(self.l_margin)
        self.multi_cell(self.w - self.l_margin - self.r_margin, self.lh,
                        clean(f'{mark} {text}'), align='R', new_x='LMARGIN', new_y='NEXT')
        self.ln(0.6)


def render(md_path: Path, out_path: Path, title: str, subtitle: str = '',
           img_root: Path | None = None) -> None:
    lines = md_path.read_text(encoding='utf-8').split('\n')
    pdf = JozePDF(title, subtitle, img_root=img_root or md_path.parent)
    pdf.add_page()

    # ---------------- جلد
    pdf.ln(28)
    pdf.set_font('Vazir', 'B', 30)
    pdf.set_text_color(*ACCENT)
    pdf.multi_cell(0, 15, title, align='C', new_x='LMARGIN', new_y='NEXT')
    if subtitle:
        pdf.ln(3)
        pdf.set_font('Vazir', '', 14)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(0, 9, subtitle, align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(6)
    pdf.set_draw_color(*ACCENT)
    pdf.set_line_width(0.7)
    pdf.line(60, pdf.get_y(), pdf.w - 60, pdf.get_y())
    pdf.ln(10)
    pdf.set_font('Vazir', '', 11.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 8.5,
                   'بازسازی‌شده از ۳۱ قطعهٔ صوتی استاد (۳۲ دقیقه و ۷ ثانیه) با رأی‌گیری شش‌جریانی؛\n'
                   'متن دقیق اسلایدها از خود فایل pptx و درجهٔ اطمینان هر بخش مشخص شده است.',
                   align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.add_page()

    i = 0
    in_code = False
    code_buf: list[str] = []
    quote_buf: list[str] = []
    table_buf: list[list[str]] = []

    def flush_quote():
        nonlocal quote_buf
        if quote_buf:
            pdf.quote(quote_buf)
            quote_buf = []

    def flush_table():
        nonlocal table_buf
        if table_buf:
            pdf.table_block(table_buf)
            table_buf = []

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        # ------------------------------------------------ بلوک کد
        if line.startswith('```'):
            if in_code:
                pdf.code_block(code_buf)
                code_buf, in_code = [], False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        # ------------------------------------------------ جدول
        if line.startswith('|') and i + 1 < len(lines) and set(lines[i + 1].replace('|', '').strip()) <= set('-: '):
            flush_quote()
            table_buf = []
            j = i
            while j < len(lines) and lines[j].startswith('|'):
                cells = [c.strip() for c in lines[j].strip().strip('|').split('|')]
                if not set(''.join(cells).replace('|', '')) <= set('-: '):
                    table_buf.append(cells)
                j += 1
            pdf.table_block(table_buf)
            table_buf = []
            i = j
            continue
        # ------------------------------------------------ تصویر
        m_img = re.match(r'^!\[(.*?)\]\((.*?)\)\s*$', line)
        if m_img:
            flush_quote()
            pdf.image_block(m_img.group(2), m_img.group(1))
            i += 1
            continue
        # ------------------------------------------------ عناوین
        if line.startswith('# '):
            flush_quote()
            pdf.start_section(clean(line[2:]), level=0)
            pdf.h1(line[2:])
        elif line.startswith('## '):
            flush_quote()
            if i > 60:               # از «فهرست» به بعد، هر سرتیتر یک bookmark
                pdf.start_section(clean(line[3:]), level=1)
            pdf.h2(line[3:])
        elif line.startswith('### '):
            flush_quote()
            pdf.h3(line[4:])
        # ------------------------------------------------ نقل‌قول
        elif line.startswith('>'):
            quote_buf.append(line)
        # ------------------------------------------------ لیست
        elif re.match(r'^\s*[-*] ', line):
            flush_quote()
            pdf.bullet(re.sub(r'^\s*[-*] ', '', line))
        elif re.match(r'^\s*\d+[.)] ', line):
            flush_quote()
            m = re.match(r'^\s*(\d+)[.)] (.*)$', line)
            pdf.bullet(m.group(2), ordered=m.group(1) + '.')
        # ------------------------------------------------ خط افقی
        elif line.strip() == '---':
            flush_quote()
            pdf.hr()
        # ------------------------------------------------ خالی
        elif not line.strip():
            flush_quote()
            i += 1
            continue
        # ------------------------------------------------ پاراگراف
        else:
            if not re.sub(r'<a id="[^"]*">\s*</a>', '', line).strip():
                i += 1
                continue
            flush_quote()
            bold = line.startswith('**') and line.count('**') >= 2 and line.endswith('**')
            txt = line
            # پیوندهای داخلی/بیرونی → فقط متن
            txt = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', txt)
            if bold:
                pdf.para(txt.strip('*'), bold=True, size=11)
            else:
                pdf.para(txt)
        i += 1
    flush_quote()
    pdf.output(str(out_path))
    print(f'✓ {out_path}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', default='جزوه')
    ap.add_argument('--subtitle', default='')
    ap.add_argument('--img-root', default=None, help='ریشهٔ مسیر تصاویر (پیش‌فرض: پوشهٔ فایل md)')
    a = ap.parse_args()
    render(Path(a.md), Path(a.out), a.title, a.subtitle,
           img_root=Path(a.img_root) if a.img_root else None)


if __name__ == '__main__':
    main()
