#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سازندهٔ جزوه
=============
از ترکیب «متن اسلایدهای پاورپوینت» + «متن پیاده‌شدهٔ صدا» یک جزوهٔ درس‌نامه‌ای
می‌سازد: چکیده، بخش‌بندی، نکات کلیدی، واژه‌نامه و خروجی HTML راست‌به‌چپ.

استفاده:
    python3 make_joze.py [--slides slides/slides.json] [--transcript out/xxx.json|xxx.txt]
                         [--title "عنوان جزوه"] [--out out]

اگر --slides ندهید، فقط از صدا جزوه ساخته می‌شود. اگر --transcript ندهید،
همهٔ فایل‌های .json/.txt موجود در پوشهٔ --transcript-dir بررسی می‌شوند.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- متن و واژه‌ها
FA_STOP = set("""
و در به از که این را با است برای آن یک خود تا هم شود بود او می بر کرد نیز وی شد
های هایش هایی هاست شدن کرده بودم بودند اگر چه بی اما یا پس چون هر همه بعضی دیگر
می‌شود می‌کند می‌کند داده دارد دارد چه چیزی آنها ایشان ما شما ایشان این‌که لذا
the a an and or but of to in is are was were be been being for on with that this
it as at by from we you they he she i not have has had do does did will would can
could should there their our your its his her them us then than so if into out up
about over under again more most some such no nor only own same too very just
all like now get got one two him them then than here don shall may might must
""".split())

EN_STOP = FA_STOP  # مشترک


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    text = re.sub(r"[«»“”\"']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟…])\s+", normalize(text))
    return [p.strip() for p in parts if len(p.strip()) > 2]


def keywords(text: str, top_n: int = 12) -> list[tuple[str, int]]:
    words = re.findall(r"[A-Za-zآ-یءأإئ۰-۹0-9‌-]{3,}", normalize(text))
    freq: dict[str, int] = {}
    for w in words:
        lw = w if re.search(r"[A-Za-z]", w) else w
        if lw.lower() in EN_STOP or w in FA_STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    return sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]


# ---------------------------------------------------------------- بارگذاری
def load_segments(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        segs = data.get("segments", [])
        return [{"t0": s.get("t0", 0.0), "text": s.get("text", "")} for s in segs if s.get("text")]
    text = path.read_text(encoding="utf-8")
    lines = []
    for m in re.finditer(r"`(\d{2}:\d{2}:\d{2})`\s*(.+)", text):
        h, mi, se = (int(x) for x in m.group(1).split(":"))
        lines.append({"t0": h * 3600 + mi * 60 + se, "text": m.group(2).strip()})
    if not lines:
        lines = [{"t0": 0.0, "text": p.strip()} for p in sentences(text)]
    return lines


def fmt_ts(t: float) -> str:
    return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d}"


# ---------------------------------------------------------------- ساخت جزوه
def build(segments: list[dict], slides_info: dict | None, title: str) -> dict:
    full_text = normalize(" ".join(s["text"] for s in segments))
    n_slides = len(slides_info["slides"]) if slides_info else 0
    sections: list[dict] = []

    if n_slides:
        # توزیع قطعه‌های صدا روی اسلایدها به نسبت زمان (یا تعداد)
        per = max(1, len(segments) // n_slides) if segments else 0
        chunk = 0
        for sl in slides_info["slides"]:
            seg_part = segments[chunk:chunk + per] if segments else []
            chunk += per
            body = sl["body"]
            excerpt = normalize(" ".join(s["text"] for s in seg_part))
            sections.append({
                "heading": f"اسلاید {sl['index']}" + (f" — {sl['title']}" if sl["title"] else ""),
                "points": body,
                "notes": sl.get("notes", ""),
                "audio": excerpt,
                "time": fmt_ts(seg_part[0]["t0"]) if seg_part else "",
            })
        if segments and chunk < len(segments):       # باقی‌مانده
            rest = segments[chunk:]
            sections.append({
                "heading": "ادامهٔ صدا",
                "points": [],
                "notes": "",
                "audio": normalize(" ".join(s["text"] for s in rest)),
                "time": fmt_ts(rest[0]["t0"]),
            })
    else:
        # بخش‌بندی بر اساس زمان (هر ~۴۵ ثانیه/۳ قطعه)
        group: list[dict] = []
        start = segments[0]["t0"] if segments else 0.0
        for s in segments:
            if group and (s["t0"] - start > 45 or len(group) >= 4):
                sections.append({"heading": f"بخش {len(sections)+1} — {fmt_ts(start)}",
                                 "points": [], "notes": "",
                                 "audio": normalize(" ".join(g["text"] for g in group)),
                                 "time": fmt_ts(start)})
                group, start = [], s["t0"]
            group.append(s)
        if group:
            sections.append({"heading": f"بخش {len(sections)+1} — {fmt_ts(start)}",
                             "points": [], "notes": "",
                             "audio": normalize(" ".join(g["text"] for g in group)),
                             "time": fmt_ts(start)})

    sents = sentences(full_text)
    abstract = " ".join(sents[:3]) if sents else full_text[:300]
    return {
        "title": title,
        "abstract": abstract,
        "sections": sections,
        "keywords": keywords(full_text, 15),
        "n_segments": len(segments),
        "duration": fmt_ts(segments[-1]["t0"] if segments else 0.0),
    }


def to_markdown(j: dict) -> str:
    L = [f"# {j['title']}", ""]
    L += ["## چکیده", "", j["abstract"], ""]
    if j["keywords"]:
        L += ["## واژه‌های کلیدی", "", "، ".join(f"**{k}** ({c})" for k, c in j["keywords"]), ""]
    L += ["---", ""]
    for s in j["sections"]:
        L += [f"## {s['heading']}"]
        if s["time"]:
            L += [f"⏱ زمان صدا: `{s['time']}`"]
        L.append("")
        if s["points"]:
            L += ["> **از اسلایدها:**", ""] + [f"- {p.lstrip('•◦ ').strip()}" for p in s["points"]] + [""]
        if s["notes"]:
            L += ["> **نُت گوینده:**", "", f"> {s['notes']}", ""]
        if s["audio"]:
            L += ["> **🎧 از صدا:**", "", f"> {s['audio']}", ""]
        L += [""]
    L += ["---", "", f"*ساخته‌شده با voice-notes | {j['n_segments']} قطعهٔ صدا | طول صدا ≈ {j['duration']}*"]
    return "\n".join(L)


HTML_TPL = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --ink:#1f2933; --muted:#52606d; --accent:#0f766e; --bg:#f8fafc; --card:#ffffff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font-family:"Vazirmatn","IRANSans","Segoe UI",Tahoma,sans-serif; line-height:2; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:32px 20px 80px; }}
  h1 {{ font-size:1.9rem; color:var(--accent); border-bottom:3px solid var(--accent); padding-bottom:12px; }}
  h2 {{ font-size:1.25rem; margin-top:36px; color:#134e4a; }}
  .meta {{ color:var(--muted); font-size:.9rem; }}
  .card {{ background:var(--card); border:1px solid #e4e7eb; border-radius:14px;
           padding:16px 20px; margin:14px 0; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
  .badge {{ display:inline-block; background:#e6fffb; color:var(--accent); border-radius:999px;
            padding:2px 10px; font-size:.8rem; margin-inline-start:8px; }}
  .label {{ font-weight:700; color:var(--accent); display:block; margin-top:10px; }}
  ul {{ margin:6px 0 6px 0; padding-inline-start:22px; }}
  .kws span {{ display:inline-block; background:#ecfdf5; border:1px solid #a7f3d0; color:#065f46;
               border-radius:8px; padding:2px 10px; margin:3px; font-size:.9rem; }}
  .audio {{ background:#f0fdfa; border-inline-start:4px solid var(--accent); border-radius:8px;
            padding:10px 14px; }}
  footer {{ margin-top:48px; color:var(--muted); font-size:.85rem; text-align:center; }}
  @media print {{ body{{background:#fff}} .card{{box-shadow:none}} }}
</style>
</head>
<body><div class="wrap">
<h1>{title}</h1>
<p class="meta">طول صدا ≈ {duration} &nbsp;•&nbsp; {n_segments} قطعهٔ صدا &nbsp;•&nbsp; {n_sections} بخش</p>
<div class="card"><span class="label">چکیده</span><p>{abstract}</p></div>
{keywords_block}
{sections_block}
<footer>ساخته‌شده با <b>voice-notes</b> — پیاده‌سازی صدا + اسلایدها</footer>
</div></body></html>
"""


def to_html(j: dict) -> str:
    esc = html.escape
    kws = ""
    if j["keywords"]:
        kws = ("<div class='card kws'><span class='label'>واژه‌های کلیدی</span>"
               + "".join(f"<span>{esc(k)} ({c})</span>" for k, c in j["keywords"])
               + "</div>")
    blocks = []
    for s in j["sections"]:
        parts = [f"<h2>{esc(s['heading'])}"]
        if s["time"]:
            parts.append(f"<span class='badge'>⏱ {esc(s['time'])}</span>")
        parts.append("</h2><div class='card'>")
        if s["points"]:
            parts.append("<span class='label'>از اسلایدها</span><ul>"
                         + "".join(f"<li>{esc(p.lstrip('•◦ '))}</li>" for p in s["points"]) + "</ul>")
        if s["notes"]:
            parts.append(f"<span class='label'>نُت گوینده</span><p>{esc(s['notes'])}</p>")
        if s["audio"]:
            parts.append(f"<span class='label'>🎧 از صدا</span><p class='audio'>{esc(s['audio'])}</p>")
        parts.append("</div>")
        blocks.append("".join(parts))
    return HTML_TPL.format(title=esc(j["title"]), duration=j["duration"], n_segments=j["n_segments"],
                           n_sections=len(j["sections"]), abstract=esc(j["abstract"]),
                           keywords_block=kws, sections_block="".join(blocks))


def main() -> None:
    ap = argparse.ArgumentParser(description="ساخت جزوه از اسلایدها + صدا")
    ap.add_argument("--slides", default=None, help="مسیر slides.json")
    ap.add_argument("--transcript", default=None, nargs="*", help="فایل‌های متن صدا (json/txt/md)")
    ap.add_argument("--transcript-dir", default="out")
    ap.add_argument("--title", default="جزوه")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    segs: list[dict] = []
    files: list[Path] = []
    if args.transcript:
        files = [Path(f).expanduser() for f in args.transcript]
    else:
        d = Path(args.transcript_dir).expanduser()
        files = sorted(p for p in d.glob("*.json") if "slides" not in p.name)
        if not files:
            files = sorted(p for p in d.glob("*.md"))
    for f in files:
        if f.exists():
            segs.extend(load_segments(f))
            print(f"  ← {f.name}: {len(segs)} قطعه (تجمعی)")

    slides_info = None
    if args.slides:
        sp = Path(args.slides).expanduser()
        if sp.exists():
            slides_info = json.loads(sp.read_text(encoding="utf-8"))
            print(f"  ← {sp.name}: {slides_info['n_slides']} اسلاید")

    if not segs and not slides_info:
        raise SystemExit("نه صدا و نه اسلایدی پیدا نشد.")

    joze = build(segs, slides_info, args.title)
    md_path = out / "joze.md"
    html_path = out / "joze.html"
    md_path.write_text(to_markdown(joze), encoding="utf-8")
    html_path.write_text(to_html(joze), encoding="utf-8")
    print(f"\n✓ جزوه ساخته شد:\n  {md_path}\n  {html_path}")


if __name__ == "__main__":
    main()
