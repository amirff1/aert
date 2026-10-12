#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
termspot_validate — آزمون جایگشتی: آیا اصطلاحِ شناسایی‌شده «ویژه» است؟
======================================================================
برای هر «شنیدهٔ» اصطلاحی که دیکود اجباری تولید کرده، دو پرسش می‌پرسیم:

  ۱) آیا متن آزادِ همان لحظه (کانال‌های مستقل + رأی‌گیری) معادلِ فارسیِ
     *همان اصطلاح* را دارد؟                      → نرخِ تأیید
  ۲) آیا معادلِ فارسیِ یک اصطلاحِ *تصادفیِ دیگر* را دارد؟ → نرخِ تصادفی

اگر نرخِ تأیید به‌طور معنادار از تصادفی بالاتر باشد، یعنی رمزگشایی اجباری
**اصطلاح درست را تشخیص داده**، نه اینکه هر بار چیزی بگوید.

۵ جایگشت تصادفی برای هر شنیده آزمایش می‌شود.
"""
from __future__ import annotations
import argparse, json, random, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import termspot_post as TP  # noqa: E402
from fa_phonetic import fa_key, TERMS  # noqa: E402

FORM_CACHE: dict[str, list[str]] = {}


def forms_of(term: str) -> list[str]:
    """معادل‌های فارسی یک اصطلاح (اگر در واژگان دامنه باشد)"""
    t = term.strip()
    if t in FORM_CACHE:
        return FORM_CACHE[t]
    out = [t]
    low = t.lower()
    for e in TERMS:
        if e['en'].lower() == low:
            out += e['fa']
    FORM_CACHE[t] = list(dict.fromkeys(out))
    return FORM_CACHE[t]


def support(term: str, t: float, t_end: float, free: list[dict], gap: float = 1.0) -> dict | None:
    cands = forms_of(term)
    for w in free:
        if w['e'] < t - gap or w['s'] > t_end + gap:
            continue
        for c in cands:
            if TP.similar(c, w['w'], 'fa'):
                return {'w': w['w'], 's': round(w['s'], 1), 'src': w['src'], 'conf': round(w['conf'], 2)}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--free', nargs='+', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--k', type=int, default=5, help='تعداد جایگشت')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--min-conf', type=float, default=0.55)
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    raw = json.loads(Path(a.raw).read_text(encoding='utf-8'))
    occ = raw['occurrences']
    free_all = TP.load_free([Path(p) for p in a.free])

    vocab = [t['en'] for t in TERMS]
    hits, perm_hits, n, perm_n = 0, 0, 0, 0
    rows, by_clip = [], defaultdict(lambda: {'n': 0, 'sup': 0, 'perm': 0, 'pk': 0})
    for o in occ:
        if o.get('conf', 0) < a.min_conf:
            continue
        canon = TP.canon_term(o['term'], o['model'])
        free = [w for w in free_all.get(o['clip'], []) if w['conf'] >= 0.3]
        if not free:
            continue
        n += 1
        ev = support(canon, o['t'], o.get('t_end', o['t']), free)
        alt = [v for v in vocab if v.lower() != canon.lower()]
        ph = 0
        pk = 0
        for _ in range(a.k):
            v = rnd.choice(alt)
            perm_n += 1
            pk += 1
            if support(v, o['t'], o.get('t_end', o['t']), free):
                ph += 1
                perm_hits += 1
        if ev:
            hits += 1
        c = by_clip[o['clip']]
        c['n'] += 1
        c['sup'] += 1 if ev else 0
        c['perm'] += ph
        c['pk'] += a.k
        rows.append({'clip': o['clip'], 't': o['t'], 'heard': o['term'], 'canon': canon,
                     'model': o['model'], 'conf': o['conf'], 'supported': bool(ev), 'evidence': ev,
                     'perm_rate': round(ph / a.k, 2)})

    Path(a.out + '.json' if not a.out.endswith('.json') else a.out).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')

    rate, prate = hits / max(1, n), perm_hits / max(1, perm_n)
    md = ['# آزمون جایگشتی اصطلاح‌ها — آیا تشخیص «ویژه» است؟', '',
          f'- شنیده‌های آزمون‌شده (اطمینان ≥ {a.min_conf}): **{n}**',
          f'- با شاهدِ متن آزاد برای **همان اصطلاح**: **{hits}** ({rate:.1%})',
          f'- با شاهدِ متن آزاد برای **اصطلاح تصادفیِ دیگر** ({a.k} جایگشت): '
          f'**{perm_hits}/{perm_n}** ({prate:.1%})',
          f'- **ضریب ویژه‌بودن: {rate/max(1e-9,prate):.2f}×**', '',
          '| قطعه | شنیده | با شاهدِ اصطلاح | نرخِ تصادفی |', '|---|---|---|---|']
    for clip, c in sorted(by_clip.items(), key=lambda kv: int(''.join(ch for ch in kv[0] if ch.isdigit()) or 0)):
        md.append(f"| {clip} | {c['n']} | {c['sup']} ({c['sup']/max(1,c['n']):.0%}) | "
                  f"{c['perm']/max(1,c['pk']):.0%} |")
    md += ['', '## نمونهٔ اصطلاح‌های تأییدشده', '']
    for r in [x for x in rows if x['supported']][:60]:
        m, s = divmod(r['t'], 60)
        md.append(f"- {r['clip']} `{int(m):02d}:{s:04.1f}` **{r['canon']}** ← شنیده «{r['heard']}» "
                  f"({r['model']}) · شاهد آزاد: «{r['evidence']['w']}» @{r['evidence']['s']}s")
    Path(a.out if a.out.endswith('.md') else a.out + '.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'✓ نمونه‌های آزمون {n} | تأییدشده {hits} ({rate:.1%}) | تصادفی {prate:.1%} → '
          f'ضریب {rate/max(1e-9,prate):.2f}×')
    print(f'   → {a.out}')


if __name__ == '__main__':
    main()
