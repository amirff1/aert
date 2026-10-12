#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
termspot_post — پالایش و «تأیید متقابل» اصطلاح‌های شناسایی‌شده
=============================================================
خروجی خام termspot.py را می‌گیرد و:

  ۱) حرف‌خوانی‌های چندتکه را یکپارچه می‌کند («کی»+«آر»+«اس» → QRS، «q»+«r»+«s» → QRS)
  ۲) هر شنیده را با **متن آزادِ ۱۰کاناله** مقابله می‌کند: اگر در همان بازهٔ زمانی،
     متن آزاد هم واژه‌ای آوایی‌هم‌خانواده شنیده باشد → ردهٔ «تأییدشده»
  ۳) رده‌بندی اعتماد: A = مدل+شاهد آزاد، B = واژهٔ انگلیسیِ متمایز یا اصطلاح بلند،
     C = تکهٔ فارسیِ کوتاهِ بی‌شاهد (کنار گذاشته می‌شود)
  ۴) خروجی: خطِ زمان نهایی (md) + JSON شواهد برای درج در جزوه
"""
from __future__ import annotations
import argparse, json, re
from collections import defaultdict
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fa_phonetic import fa_key, en_key, TERMS  # noqa: E402

# ---------------------------------------------------------------- یکپارچه‌سازی
READING_TABLE = {
    'qrs': ['q r s', 'q r s'.replace(' ', ''), 'کیو آر اس', 'کیو ار اس', 'کی آر اس', 'کیارس',
            'کی یو آر اس', 'کیوارس', 'قورس', 'کیواس', 'كيو ار اس'],
    'pr': ['p r', 'پی آر', 'پیر', 'پیار'],
    'st': ['s t', 'اس تی', 'استی'],
    'qt': ['q t', 'کیو تی', 'کیوتی'],
    'wpw': ['w p w', 'دبلیو پی دبلیو'],
    'mi': ['m i', 'ام آی', 'ام‌آی'],
    'bbb': ['b b b', 'بی بی بی'],
    'lbbb': ['l b b', 'ال بی بی'],
    'rbbb': ['r b b', 'آر بی بی'],
    'v1': ['وی یک', 'v one'], 'v2': ['وی دو', 'v two'], 'v3': ['وی سه', 'v three'],
    'v4': ['وی چهار', 'v four'], 'v5': ['وی پنج', 'v five'], 'v6': ['وی شش', 'v six'],
}
CANON = {reading: canon for canon, readings in READING_TABLE.items() for reading in readings}
DISPLAY = {'qrs': 'QRS', 'pr': 'PR', 'st': 'ST', 'qt': 'QT', 'wpw': 'WPW', 'mi': 'MI',
           'bbb': 'BBB', 'lbbb': 'LBBB', 'rbbb': 'RBBB'}
for i in range(1, 7):
    DISPLAY[f'v{i}'] = f'V{i}'

# اصطلاح‌های «کوتاه/عمومی» فارسی که بی‌شاهدِ متن آزاد پذیرفته نمی‌شوند
GENERIC = {'موج', 'ناحیه', 'بالا', 'پایین', 'راست', 'چپ', 'قلب', 'لید', 'لیدها', 'کی', 'پی',
           'تی', 'اس', 'کیو', 'فول', 'استاندارد', 'شمارش', 'گذر', 'انحراف', 'تاخیر', 'نود',
           'ریتم', 'سینوس', 'اینتروال', 'سگمنت', 'نرمال', 'بلاک', 'سیگنال', 'مانیتور'}
EN_OK_ALWAYS = True      # واژهٔ انگلیسیِ شناسایی‌شده با مدل en ارزش بالا دارد


def load_free(paths: list[Path]) -> dict[str, list[dict]]:
    """متن آزاد همهٔ کانال‌ها → {clip: [words]} برای مقابلهٔ آوایی"""
    out: dict[str, list[dict]] = defaultdict(list)
    for p in paths:
        if not p.exists():
            continue
        if p.is_dir():
            for f in sorted(p.glob('media*.json')):
                d = json.loads(f.read_text(encoding='utf-8'))
                for ch, words in d.items():
                    for w in words:
                        out[f.stem].append({'w': w['word'], 's': w['start'], 'e': w['end'],
                                            'conf': w.get('conf', 0), 'src': ch})
        else:
            d = json.loads(p.read_text(encoding='utf-8'))
            for clip, rec in d.items():
                for w in rec.get('words', []):
                    out[clip].append({'w': w['word'], 's': w['start'], 'e': w['end'],
                                      'conf': w.get('conf', 0), 'src': 'rover'})
    return out


def fa_forms(canon: str) -> list[str]:
    for t in TERMS:
        if t['en'].lower() == canon:
            return t['fa'] + [canon]
    return [canon]


def key_of(text: str, lang: str) -> str:
    return fa_key(text) if lang == 'fa' else en_key(text)


def similar(a: str, b: str, lang: str) -> bool:
    if not a or not b:
        return False
    ka, kb = key_of(a, lang), key_of(b, lang)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    if abs(len(ka) - len(kb)) <= 1:
        # یک خطای ویرایشی
        if len(ka) > len(kb):
            ka, kb = kb, ka
        i = j = d = 0
        while i < len(ka) and j < len(kb):
            if ka[i] != kb[j]:
                d += 1
                if d > 1:
                    return False
                if len(ka) == len(kb):
                    i += 1
                j += 1
            else:
                i += 1
                j += 1
        return True
    return False


def canon_term(term: str, model: str) -> str:
    k = term.strip().lower()
    if k in CANON:
        return CANON[k]
    return term.strip()


def group_letters(occ: list[dict], gap: float = 0.6) -> list[dict]:
    """تکه‌های پشت‌سرهمِ حرف‌خوانی را یکی می‌کند (q + r + s → qrs)"""
    occ = sorted(occ, key=lambda o: o['t'])
    used = [False] * len(occ)
    out = []
    for i, o in enumerate(occ):
        if used[i]:
            continue
        if o['model'] == 'en' and len(o['term'].strip()) == 1:
            chain = [o]
            for j in range(i + 1, len(occ)):
                if used[j] or occ[j]['model'] != 'en':
                    continue
                if occ[j]['t'] - chain[-1]['t'] <= gap and len(occ[j]['term'].strip()) == 1:
                    chain.append(occ[j])
                    used[j] = True
                    if len(chain) >= 3:
                        break
            if len(chain) > 1:
                joined = ''.join(c['term'].strip().lower() for c in chain)
                used[i] = True
                out.append({'clip': o['clip'], 't': chain[0]['t'], 't_end': chain[-1]['t'],
                            'term': joined, 'conf': round(sum(c['conf'] for c in chain) / len(chain), 3),
                            'model': 'en', 'hits': sum(c['hits'] for c in chain), 'chain': True})
                continue
        used[i] = True
        out.append(dict(o))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--free', nargs='+', required=True)
    ap.add_argument('--out-md', required=True)
    ap.add_argument('--out-json', required=True)
    a = ap.parse_args()

    raw = json.loads(Path(a.raw).read_text(encoding='utf-8'))
    free = load_free([Path(p) for p in a.free])
    occ = raw['occurrences']

    by_clip: dict[str, list[dict]] = defaultdict(list)
    for o in occ:
        by_clip[o['clip']].append(o)

    findings, dropped = [], 0
    for clip, items in by_clip.items():
        items = group_letters(items)
        fw = [w for w in free.get(clip, []) if w['conf'] >= 0.3]
        for o in items:
            canon = canon_term(o['term'], o['model'])
            if canon == '[unk]':
                continue
            lang = 'en' if (o['model'] == 'en' or re.fullmatch(r'[A-Za-z ]+', o['term'] or '')) else 'fa'
            forms = [o['term']] + (fa_forms(canon) if len(canon) <= 6 else [])
            # شاهدِ متن آزاد: واژه‌ای هم‌خانواده در همان بازهٔ زمانی
            ev = []
            for w in fw:
                if w['e'] < o['t'] - 1.1 or w['s'] > o.get('t_end', o['t']) + 1.1:
                    continue
                for f in forms:
                    if similar(f, w['w'], lang):
                        ev.append({'w': w['w'], 's': round(w['s'], 1), 'src': w['src'],
                                   'conf': round(w['conf'], 2)})
                        break
            long_term = len(o['term']) >= 6
            if ev:
                tier = 'A'
            elif o['model'] == 'en' or (long_term and o['conf'] >= 0.75):
                tier = 'B'
            elif o['term'] in GENERIC and o['conf'] < 0.9:
                tier = 'C'
            else:
                tier = 'B' if o['hits'] >= 2 else 'C'
            if tier == 'C':
                dropped += 1
                continue
            findings.append({'clip': clip, 't': o['t'], 't_end': o.get('t_end', o['t']),
                             'heard': o['term'], 'canon': canon, 'display': DISPLAY.get(canon, canon),
                             'model': o['model'], 'conf': o['conf'], 'hits': o['hits'],
                             'tier': tier, 'evidence': ev[:4]})

    findings.sort(key=lambda f: (int(re.sub(r'\D', '', f['clip'])), f['t']))
    Path(a.out_json).write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding='utf-8')

    # ------------------------------------------------------------------ گزارش
    per_clip: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        per_clip[f['clip']].append(f)
    glossary: dict[str, dict] = {}
    for f in findings:
        g = glossary.setdefault(f['display'], {'n': 0, 'clips': set(), 'best': 0, 'A': 0, 'B': 0})
        g['n'] += 1
        g['clips'].add(f['clip'])
        g['best'] = max(g['best'], f['conf'])
        g[f['tier']] += 1

    md = ['# خطِ زمانِ اصطلاح‌های تخصصی (شنیدهٔ استاد)', '',
          '> **روش:** رمزگشایی اجباری (grammar) با دو مدل Vosk روی پنجره‌های هم‌پوشان + '
          'تأیید متقابل با متن آزادِ ۱۰کانالهٔ همان لحظه.',
          '> **ردهٔ A** = هم مدل اجباری، هم متن آزاد در همان لحظه شاهد دارند · '
          '**ردهٔ B** = واژهٔ انگلیسیِ متمایز یا اصطلاح بلند با اطمینان بالا · '
          'ردهٔ C (بی‌شاهد) حذف شده است.', '']
    nA = sum(1 for f in findings if f['tier'] == 'A')
    nB = len(findings) - nA
    md += [f'- شنیده‌های پذیرفته‌شده: **{len(findings)}** (ردهٔ A: {nA} · ردهٔ B: {nB}) · '
           f'حذف‌شده به‌خاطر بی‌شاهدی: {dropped}', '',
           '## واژه‌نامهٔ اصطلاح‌ها', '',
           '| اصطلاح شنیده‌شده | تعداد | ردهٔ A | قطعه‌ها |', '|---|---|---|---|']
    for term, g in sorted(glossary.items(), key=lambda kv: (-kv[1]['n'], kv[0])):
        cs = '، '.join(sorted(g['clips'], key=lambda c: int(re.sub(r'\D', '', c))))
        md.append(f"| **{term}** | {g['n']} | {g['A']} | {cs} |")
    md += ['', '## خطِ زمان به تفکیک قطعه', '']
    for clip in sorted(per_clip, key=lambda c: int(re.sub(r'\D', '', c))):
        md += [f'### {clip}', '']
        for f in per_clip[clip]:
            m, s = divmod(f['t'], 60)
            ev = f" ✔ «{f['evidence'][0]['w']}» در متن آزاد @{f['evidence'][0]['s']}s" if f['evidence'] else ''
            md.append(f"- `{int(m):02d}:{s:04.1f}` **{f['display']}** — شنیده: «{f['heard']}» "
                      f"({f['model']} · اطمینان {f['conf']} · {f['hits']} پنجره · ردهٔ {f['tier']}){ev}")
        md.append('')
    Path(a.out_md).write_text('\n'.join(md), encoding='utf-8')
    print(f'✓ پذیرفته {len(findings)} (A={nA} B={nB}) · حذف‌شده {dropped} · '
          f'اصطلاح متمایز {len(glossary)}')
    top = sorted(glossary.items(), key=lambda kv: -kv[1]['n'])[:12]
    print('   پرتکرار:', '، '.join(f'{k}({v["n"]})' for k, v in top))


if __name__ == '__main__':
    main()
