#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2html — تبدیل مارک‌داون جزوه به HTML راست‌به‌چپ و آمادهٔ چاپ.
پشتیبانی: سرتیترها، پاراگراف، لیست، جدول، نقل‌قول، بلوک کد، پررنگ/مورب، خط افقی.

استفاده:  python3 md2html.py joze.md [--out joze.html] [--title «عنوان»]
"""
from __future__ import annotations
import argparse, html, re
from pathlib import Path

CSS = """
  :root { --ink:#1f2933; --muted:#52606d; --accent:#0f766e; --accent2:#b45309;
          --bg:#f8fafc; --card:#fff; --line:#e4e7eb; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); line-height:2;
         font-family:"Vazirmatn","IRANSans","Segoe UI",Tahoma,sans-serif; }
  .wrap { max-width:960px; margin:0 auto; padding:36px 22px 90px; }
  h1 { font-size:2rem; color:var(--accent); border-bottom:3px solid var(--accent);
       padding-bottom:12px; margin-bottom:6px; }
  h2 { font-size:1.4rem; margin-top:44px; color:#134e4a; border-inline-start:5px solid var(--accent);
       padding-inline-start:12px; }
  h3 { font-size:1.12rem; margin-top:26px; color:#0e7490; }
  h4 { font-size:1rem; margin-top:20px; }
  p { margin:10px 0; }
  a { color:var(--accent); }
  table { border-collapse:collapse; width:100%; margin:14px 0; background:var(--card);
          box-shadow:0 1px 2px rgba(0,0,0,.04); font-size:.95rem; }
  th,td { border:1px solid var(--line); padding:8px 12px; text-align:right; vertical-align:top; }
  th { background:#ecfdf5; color:#065f46; font-weight:700; }
  tr:nth-child(even) td { background:#fbfdfc; }
  ul,ol { padding-inline-start:24px; margin:8px 0; }
  li { margin:4px 0; }
  blockquote { margin:16px 0; background:#f0fdfa; border-inline-start:4px solid var(--accent);
               border-radius:10px; padding:12px 16px; color:#134e4a; }
  blockquote p { margin:6px 0; }
  code { background:#f1f5f9; border:1px solid var(--line); border-radius:6px;
         padding:1px 6px; font-family:ui-monospace,Menlo,Consolas,monospace; direction:ltr;
         display:inline-block; font-size:.9em; }
  pre { background:#0f172a; color:#e2e8f0; padding:14px 16px; border-radius:12px;
        overflow-x:auto; direction:ltr; text-align:left; }
  pre code { background:none; border:none; color:inherit; padding:0; }
  hr { border:none; border-top:2px dashed var(--line); margin:36px 0; }
  strong { color:#0b3d3a; }
  .meta { color:var(--muted); font-size:.9rem; }
  footer { margin-top:60px; color:var(--muted); font-size:.85rem; text-align:center;
           border-top:1px solid var(--line); padding-top:18px; }
  @media print { body{background:#fff} h2{page-break-after:avoid} table,blockquote{page-break-inside:avoid} }
"""


def inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def convert(md: str) -> str:
    out: list[str] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()

        if not s:
            i += 1
            continue

        # code fence
        if s.startswith("```"):
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i]); i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(body)) + "</code></pre>")
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        # hr
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            out.append("<hr>")
            i += 1
            continue

        # table
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            header = [c.strip() for c in s.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<table><thead><tr>"] + [f"<th>{inline(h)}</th>" for h in header] + ["</tr></thead><tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        # blockquote (collect contiguous > lines)
        if s.startswith(">"):
            body = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                body.append(lines[i].strip().lstrip(">").strip())
                i += 1
            inner = "".join(f"<p>{inline(b)}</p>" for b in body if b)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # lists
        if re.match(r"^\s*[-*+]\s+", ln) or re.match(r"^\s*\d+[.)]\s+", ln):
            ordered = bool(re.match(r"^\s*\d+[.)]\s+", ln))
            items = []
            while i < len(lines) and (re.match(r"^\s*[-*+]\s+", lines[i]) or re.match(r"^\s*\d+[.)]\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        # paragraph
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#|\||>|\s*[-*+]\s|\s*\d+[.)]\s|```)", lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return "\n".join(out)


TPL = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body><div class="wrap">
{body}
<footer>ساخته‌شده با <b>voice-notes</b> — پیاده‌سازی صدا + اسلایدها</footer>
</div></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="مارک‌داون → HTML راست‌به‌چپ")
    ap.add_argument("md")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default=None)
    args = ap.parse_args()
    src = Path(args.md).expanduser()
    text = src.read_text(encoding="utf-8")
    m = re.search(r"^#\s+(.*)$", text, re.M)
    title = args.title or (m.group(1) if m else src.stem)
    dst = Path(args.out).expanduser() if args.out else src.with_suffix(".html")
    dst.write_text(TPL.format(title=html.escape(title), css=CSS, body=convert(text)), encoding="utf-8")
    print(f"✓ {dst}")


if __name__ == "__main__":
    main()
