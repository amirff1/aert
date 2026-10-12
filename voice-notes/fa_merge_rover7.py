#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_merge_rover7 — رأی‌گیری نسل هفت با «وزنِ کانال»
=================================================
کانال‌ها: ۴ جریانِ fa5 + ۲ جریانِ تازهٔ fa7 (گیتینگِ طیفی) + متنِ رأی‌گیری‌شدهٔ v3
(۷ منبع رأی). دو حالت محاسبه می‌شود:

  ۱) رأیِ برابر (مثل قبل)
  ۲) رأیِ **وزنی**: وزن هر کانال = توافقش با متنِ رأی‌گیریِ مرحلهٔ اول × میانگین اطمینانش.
     (کانالی که «خودسر» است وزن کم می‌گیرد؛ دو مرحله‌ای محاسبه می‌شود)

خروجی: transcript-fa-v7.json (نسخهٔ برنده) + گزارش مقایسه با v5
"""
from __future__ import annotations
import json, re, sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

W = Path('/home/user/work/zadkamali')
DIRS = [('s5', W / 'fa5_out' / 'streams'), ('s7', W / 'fa7_out' / 'streams')]
V3 = Path('/home/user/aert/voice-notes/zadkamali/transcript-fa-v3.json')
V5 = W / 'transcript-fa-final.json'


def norm_w(w: str) -> str:
    w = w.strip().replace('\u200c', '')
    return re.sub(r'[^\w\u0600-\u06FF]+', '', w).lower()


def rover(streams: dict[str, list[dict]], weights: dict[str, float] | None = None):
    names = [k for k, v in streams.items() if v]
    if not names:
        return [], {}
    weights = weights or {k: 1.0 for k in names}
    ref_name = max(names, key=lambda k: len(streams[k]))
    ref = streams[ref_name]
    used = {k: [False] * len(streams[k]) for k in names}
    slots = []
    for ri, rw in enumerate(ref):
        slot = {ref_name: rw}
        used[ref_name][ri] = True
        rc = (rw['start'] + rw['end']) / 2.0
        tol = max(0.28, (rw['end'] - rw['start']) / 2.0 + 0.10)
        for k in names:
            if k == ref_name:
                continue
            best, bi, bov = None, -1, None
            for j, w in enumerate(streams[k]):
                if used[k][j]:
                    continue
                if abs((w['start'] + w['end']) / 2.0 - rc) > tol:
                    continue
                ov = min(rw['end'], w['end']) - max(rw['start'], w['start'])
                if best is None or ov > bov:
                    best, bi, bov = w, j, ov
            if best is not None:
                slot[k] = best
                used[k][bi] = True
        slots.append(slot)
    spans = [(min(w['start'] for w in sl.values()), max(w['end'] for w in sl.values())) for sl in slots]
    leftovers = []
    for k in names:
        for j, w in enumerate(streams[k]):
            if used[k][j]:
                continue
            if any(not (w['end'] < a or w['start'] > b) for a, b in spans):
                continue
            leftovers.append((k, w))
    leftovers.sort(key=lambda kv: kv[1]['start'])
    for k, w in leftovers:
        slots.append({k: w})
    slots.sort(key=lambda sl: min(w['start'] for w in sl.values()))

    per_channel: dict[str, int] = defaultdict(int)
    merged = []
    for sl in slots:
        votes: dict[str, dict] = {}
        for name, w in sl.items():
            key = norm_w(w['word'])
            if not key:
                continue
            d = votes.setdefault(key, {'text': w['word'], 'wsum': 0.0, 'streams': set(),
                                       'confs': [], 'start': w['start'], 'end': w['end']})
            d['wsum'] += weights.get(name, 1.0)
            d['streams'].add(name)
            d['confs'].append(w['conf'])
            d['start'] = min(d['start'], w['start'])
            d['end'] = max(d['end'], w['end'])
        if not votes:
            continue

        def key_fn(kv):
            k, d = kv
            return (round(d['wsum'], 4), len(d['streams']), round(float(np.mean(d['confs'])), 4), len(k))
        bk, best = max(votes.items(), key=key_fn)
        for s in best['streams']:
            per_channel[s] += 1
        merged.append({'word': best['text'], 'norm': bk, 'votes': len(best['streams']),
                       'wsum': round(best['wsum'], 2), 'conf': round(float(np.mean(best['confs'])), 3),
                       'start': round(best['start'], 2), 'end': round(best['end'], 2),
                       'alts': [{'w': k, 'v': len(d['streams']), 'c': round(float(np.mean(d['confs'])), 3)}
                                for k, d in sorted(votes.items(), key=key_fn, reverse=True) if k != bk][:3]})
    out = []
    for w in merged:
        if out and out[-1]['norm'] == w['norm']:
            out[-1]['votes'] = max(out[-1]['votes'], w['votes'])
            continue
        out.append(w)
    return out, per_channel


def load_clip(name: str) -> dict[str, list[dict]]:
    streams = {}
    for tag, d in DIRS:
        p = d / f'{name}.json'
        if p.exists():
            for k, v in json.loads(p.read_text(encoding='utf-8')).items():
                streams[f'{tag}:{k}'] = v
    if V3.exists():
        d = json.loads(V3.read_text(encoding='utf-8'))
        if name in d and d[name].get('words'):
            streams['prev:v3'] = d[name]['words']
    return streams


def f1(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    m = sum(bl.size for bl in sm.get_matching_blocks())
    return 2 * m / (len(a) + len(b))


def stats_of(words: list[dict]) -> dict:
    n = len(words)
    return {'n_words': n,
            'vote2plus': sum(1 for w in words if w['votes'] >= 2),
            'vote3plus': sum(1 for w in words if w['votes'] >= 3),
            'low': sum(1 for w in words if w['votes'] < 2 or w['conf'] < 0.6),
            'agree_ratio': round(sum(1 for w in words if w['votes'] >= 2) / max(1, n), 3),
            'low_ratio': round(sum(1 for w in words if w['votes'] < 2 or w['conf'] < 0.6) / max(1, n), 3)}


def main() -> None:
    v5 = json.loads(V5.read_text(encoding='utf-8')) if V5.exists() else {}
    clips = [f'media{i}' for i in range(1, 32)]
    # ---------- مرحلهٔ ۱: رأیِ برابر
    pass1, streams_all = {}, {}
    for name in clips:
        streams = load_clip(name)
        streams_all[name] = streams
        words, _ = rover(streams)
        pass1[name] = words
    # ---------- وزن کانال‌ها با توافق با متنِ مرحلهٔ ۱
    wsum: dict[str, list[float]] = defaultdict(list)
    for name in clips:
        ref = [w['word'] for w in pass1[name]]
        for k, words in streams_all[name].items():
            if not words:
                continue
            wsum[k].append(f1([w['word'] for w in words], ref))
    weights = {k: round(max(0.2, float(np.mean(v))), 3) for k, v in wsum.items()}
    print('وزنِ کانال‌ها (توافق با رأیِ مرحلهٔ ۱):',
          ' · '.join(f'{k}={v}' for k, v in sorted(weights.items(), key=lambda kv: -kv[1])))

    result, rows, totals = {}, [], defaultdict(int)
    for name in clips:
        words, per_ch = rover(streams_all[name], weights)
        st = stats_of(words)
        result[name] = {'media': name, 'text': ' '.join(w['word'] for w in words),
                        'words': words, 'stats': st}
        old = v5.get(name, {}).get('words', [])
        old_st = stats_of(old) if old else {}
        rows.append((name, old_st, st, len(streams_all[name])))
        for k in ('n_words', 'vote2plus', 'vote3plus', 'low'):
            totals[f'new_{k}'] += st[k]
            totals[f'old_{k}'] += old_st.get(k, 0)

    (W / 'transcript-fa-v7.json').write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                             encoding='utf-8')
    print(f"\n{'قطعه':9s} {'واژه':>6s} {'≥۲v قدیم→نو':>16s} {'کم‌اطمینان قدیم→نو':>22s}")
    for name, old, new, nch in rows:
        print(f"{name:9s} {new['n_words']:6d} "
              f"{old.get('vote2plus',0):6d}→{new['vote2plus']:5d} "
              f"({old.get('agree_ratio',0):.0%}→{new['agree_ratio']:.0%})   "
              f"{old.get('low',0):5d}→{new['low']:5d} ({old.get('low_ratio',0):.0%}→{new['low_ratio']:.0%})")
    print(f"\nجمع: واژه {totals['old_n_words']}→{totals['new_n_words']} | "
          f"≥۲ رأی {totals['old_vote2plus']}→{totals['new_vote2plus']} "
          f"({totals['old_vote2plus']/max(1,totals['old_n_words']):.1%}→{totals['new_vote2plus']/max(1,totals['new_n_words']):.1%}) | "
          f"کم‌اطمینان {totals['old_low']}→{totals['new_low']} "
          f"({totals['old_low']/max(1,totals['old_n_words']):.1%}→{totals['new_low']/max(1,totals['new_n_words']):.1%})")
    # کانال‌های پرکاربرد
    print('✓ transcript-fa-v7.json')


if __name__ == '__main__':
    main()
