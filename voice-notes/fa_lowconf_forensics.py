#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_lowconf_forensics — بازبینی قانونیِ واژه‌های کم‌اطمینان
=========================================================
برای هر واژهٔ کم‌اطمینان در متنِ نهایی (رأی‌گیری)، همهٔ کانال‌های خام را در
همان بازهٔ زمانی (±۰٫۴ ثانیه) جست‌وجو می‌کند:

  • اگر کانالی «دقیقاً» یک واژهٔ تخصصی دامنه را شنیده باشد  → شاهد مستقیم
  • اگر کانالی واژه‌ای شنیده باشد که آوایی ≈ واژهٔ تخصصی است → شاهد آوایی
  • اگر خودِ واژهٔ رأی‌گیری‌شده ≈ واژهٔ تخصصی باشد            → پیشنهاد آوایی

خروجی: گزارش مارک‌داون + JSON یافته‌ها (برای علامت‌گذاری در جزوه)
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from pathlib import Path
from fa_phonetic import build_default, fa_key, en_key

TOL = 0.45     # پنجرهٔ زمانی هم‌پوشانی (ثانیه)


def load_streams(root: Path) -> dict[str, dict]:
    """{mediaN: {channel: [words]}}"""
    out: dict[str, dict] = {}
    for f in sorted(root.glob('media*.json')):
        out[f.stem] = json.loads(f.read_text(encoding='utf-8'))
    return out


def overlapping(words: list[dict], s: float, e: float):
    return [w for w in words if w['end'] > s - TOL and w['start'] < e + TOL]


def match_term(word: str, L) -> str | None:
    """آیا این واژهٔ فارسی/انگلیسی به واژهٔ تخصصی می‌خورد؟ (آوایی)"""
    if not word:
        return None
    r = L.best_persian(word)
    if r:
        return r[1]
    # واژه‌های انگلیسیِ رونویسی‌شده با الفبای فارسی هم گاهی درست می‌آیند
    if re.fullmatch(r'[A-Za-z]+', word):
        r2 = L.best_english(word)
        if r2:
            return r2[1]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--final', required=True)
    ap.add_argument('--streams', required=True)
    ap.add_argument('--v3', default='')
    ap.add_argument('--out-md', required=True)
    ap.add_argument('--out-json', required=True)
    ap.add_argument('--min-votes', type=int, default=2)
    ap.add_argument('--min-conf', type=float, default=0.6)
    a = ap.parse_args()

    L = build_default()
    raw = json.loads(Path(a.final).read_text(encoding='utf-8'))
    streams = load_streams(Path(a.streams))
    v3 = json.loads(Path(a.v3).read_text(encoding='utf-8')) if a.v3 and Path(a.v3).exists() else {}

    findings, per_clip = [], defaultdict(lambda: {'shaky': 0, 'direct': 0, 'phon': 0, 'sug': 0})
    for clip in sorted(raw, key=lambda k: int(re.sub(r'\D', '', k) or 0)):
        for w in raw[clip]['words']:
            if w['votes'] >= a.min_votes and w['conf'] >= a.min_conf:
                continue
            per_clip[clip]['shaky'] += 1
            s, e = w['start'], w['end']
            heard: list[tuple[str, str, float]] = []      # (کانال، واژه، conf)
            for ch, words in (streams.get(clip, {}) or {}).items():
                for o in overlapping(words, s, e):
                    heard.append((ch, o['word'], o.get('conf', 0)))
            if v3.get(clip):
                for o in overlapping(v3[clip]['words'], s, e):
                    heard.append(('رأی‌گیری قبلی', o['word'], o.get('conf', 0)))

            direct = sorted({w2 for _, w2, _ in heard if match_term(w2, L) == (sug := match_term(w['word'], L)) and sug})
            phonic = sorted({w2 for _, w2, _ in heard if match_term(w2, L) and match_term(w2, L) != sug})
            sug = match_term(w['word'], L)
            if sug and direct:
                tag = 'شاهد مستقیم'
                per_clip[clip]['direct'] += 1
            elif sug:
                tag = 'پیشنهاد آوایی'
                per_clip[clip]['sug'] += 1
            elif phonic and any(match_term(w2, L) for _, w2, _ in heard):
                tag = 'شنیدهٔ کانال‌ها'
                per_clip[clip]['phon'] += 1
            else:
                tag = '—'
            if tag != '—' or phonic:
                findings.append({
                    'clip': clip, 'start': round(s, 2), 'end': round(e, 2),
                    'word': w['word'], 'votes': w['votes'], 'conf': round(w['conf'], 2),
                    'alts': [x['w'] for x in (w.get('alts') or [])[:3]],
                    'suggestion': sug, 'direct_evidence': direct,
                    'channel_terms': phonic, 'tag': tag,
                    'heard': [{'ch': c, 'w': x, 'conf': round(cf, 2)} for c, x, cf in heard[:14]],
                })

    # ---------------------------------------------------------------- report
    n_sug = sum(1 for f in findings if f['tag'] == 'پیشنهاد آوایی')
    n_dir = sum(1 for f in findings if f['tag'] == 'شنیدهٔ کانال‌ها' or f['direct_evidence'])
    n_all = sum(p['shaky'] for p in per_clip.values())
    md = ['# بازبینی واژه‌های کم‌اطمینان — شواهد کانالی و آوایی', '',
          f'- کل واژه‌های کم‌اطمینان: **{n_all}**',
          f'- واژه‌هایی که **شاهد مستقیم** دارند (کانالی واژهٔ تخصصی را شنیده): **{n_dir}**',
          f'- **پیشنهاد آوایی** روی واژهٔ رأی‌گیری: **{n_sug}**', '']
    md += ['| قطعه | زمان | واژهٔ خام | رأی | اطمینان | پیشنهاد | شاهد مستقیم | شنیدهٔ کانال‌ها |',
           '|---|---|---|---|---|---|---|---|']
    for f in sorted(findings, key=lambda x: (int(re.sub(r'\D', '', x['clip'])), x['start'])):
        md.append(f"| {f['clip']} | {f['start']:.1f}s | ‹{f['word']}› | {f['votes']} | {f['conf']} | "
                  f"{f['suggestion'] or '—'} | {('، '.join(f['direct_evidence']) or '—')} | "
                  f"{('، '.join(f['channel_terms'][:4]) or '—')} |")
    md += ['', '## جزئیات شنیده‌های هر واژه', '']
    for f in findings:
        hs = ' · '.join(f"{h['ch']}: «{h['w']}»" for h in f['heard'])
        md.append(f"- **{f['clip']} @{f['start']}s** — خام ‹{f['word']}› → {f['tag']}"
                  f"{' → ' + f['suggestion'] if f['suggestion'] else ''}\n  - {hs}")
    Path(a.out_md).write_text('\n'.join(md), encoding='utf-8')
    Path(a.out_json).write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'✓ گزارش: {a.out_md}')
    print(f'   کم‌اطمینان {n_all} | شاهد مستقیم/کانالی {n_dir} | پیشنهاد آوایی {n_sug} | یافته‌ها {len(findings)}')
    worst = sorted(per_clip.items(), key=lambda kv: -kv[1]['shaky'])[:5]
    print('   قطعه‌های بدتر:', ', '.join(f'{k}({v["shaky"]})' for k, v in worst))


if __name__ == '__main__':
    main()
