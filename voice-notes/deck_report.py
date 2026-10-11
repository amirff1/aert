#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deck_report — گزارش اسلاید‌به‌اسلاید یک ارائهٔ صدادار
=====================================================
ورودی:  slides_raw.json  (متن اسلایدها)  +  پوشهٔ خروجی ASR (media*.json)
        +  media_to_slide.json (نقشهٔ فایل صوتی → شمارهٔ اسلاید)
خروجی:  slides-en.md، transcript-fa.md، transcript-fa.json، deck.json

استفاده:
    python3 deck_report.py --work DIR [--out DIR]
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path


def ts(t: float) -> str:
    return f"{int(t//60):02d}:{int(t%60):02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description="گزارش اسلاید‌به‌اسلاید ارائهٔ صدادار")
    ap.add_argument("--work", required=True, help="پوشهٔ کاری شامل slides_raw.json و پوشهٔ ASR")
    ap.add_argument("--asr-dir", default="fa_out")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    work = Path(args.work).expanduser()
    out = Path(args.out).expanduser() if args.out else work
    slides = json.loads((work / "slides_raw.json").read_text(encoding="utf-8"))
    m2s = json.loads((work / "media_to_slide.json").read_text(encoding="utf-8"))
    s2m: dict[str, list[str]] = {}
    for media, slide in m2s.items():
        s2m.setdefault(slide, []).append(media)

    asr_dir = work / args.asr_dir
    narr: dict[str, dict] = {}
    for p in sorted(asr_dir.glob("media*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        narr[d["media"]] = d

    # ---- slides-en.md
    L = ["# متن اسلایدها (انگلیسی)", ""]
    for s in slides:
        L.append(f"## Slide {s['i']}" + (f" — {s['text'][0]}" if s["text"] else ""))
        L.append("")
        for t in s["text"][1:] if len(s["text"]) > 1 else s["text"]:
            L.append(f"- {t}")
        if s.get("notes"):
            L.append("")
            L.append("> 🗒️ notes: " + " / ".join(s["notes"]))
        L.append("")
    (out / "slides-en.md").write_text("\n".join(L), encoding="utf-8")

    # ---- transcript-fa.md  (اسلاید به اسلاید)
    T = ["# پیاده‌سازی روایت استاد (فارسی)", "",
         "> مدل: Vosk فارسی — متن خام و تقریبی است؛ برای نقل‌قول دقیق به فایل صوتی مراجعه کنید.", ""]
    full = []
    for s in slides:
        idx = str(s["i"])
        medias = sorted(s2m.get(idx, []))
        if not medias:
            continue
        for m in medias:
            d = narr.get(m)
            if not d:
                continue
            T.append(f"### 🎧 اسلاید {idx} — {m}")
            if s["text"]:
                T.append(f"*اسلاید:* {' | '.join(s['text'][:4])}")
            T.append("")
            if d["segments"]:
                for seg in d["segments"]:
                    T.append(f"- `{ts(seg['t0'])}–{ts(seg['t1'])}` {seg['text']}")
            else:
                T.append("- (بدون گفتار قابل‌تشخیص)")
            T.append("")
            full.append({"slide": int(idx), "media": m, "text": d["text"],
                         "segments": d["segments"]})
    (out / "transcript-fa.md").write_text("\n".join(T), encoding="utf-8")
    json.dump(full, (out / "transcript-fa.json").open("w"), ensure_ascii=False, indent=1)

    # ---- deck.json  (ساختار یکپارچه)
    deck = []
    for s in slides:
        idx = str(s["i"])
        med = sorted(s2m.get(idx, []))
        deck.append({
            "slide": s["i"], "text": s["text"], "notes": s.get("notes", []),
            "audio": med,
            "narration": " ".join(narr[m]["text"] for m in med if m in narr),
        })
    json.dump(deck, (out / "deck.json").open("w"), ensure_ascii=False, indent=1)

    n_audio = sum(1 for d in deck if d["audio"])
    total_chars = sum(len(d["narration"]) for d in deck)
    print(f"✓ {len(deck)} اسلاید | {n_audio} اسلاید با روایت | {total_chars} کاراکتر متن فارسی")
    print(f"  {out/'slides-en.md'}\n  {out/'transcript-fa.md'}\n  {out/'transcript-fa.json'}\n  {out/'deck.json'}")


if __name__ == "__main__":
    main()
