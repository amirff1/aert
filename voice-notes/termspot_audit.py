#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
termspot_audit — سنجش «توهم» رمزگشایی اجباری با گرامر کنترل
============================================================
اگر رمزگشایی اجباری هر جا چیزی تولید کند (توهم)، پس با یک گرامرِ **کنترل**
(واژه‌های رایج و بی‌ربط فارسی/انگلیسی با طول مشابه) هم باید به همان نرخ
«شنیده» تولید کند. این اسکریپت همان بازه‌ها را با گرامر کنترل و گرامر
اصطلاح‌ها می‌سنجد و نرخِ hit و توزیع اطمینان را کنار هم می‌گذارد.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import termspot  # noqa: E402

CONTROL_FA = ['کتاب', 'مدرسه', 'درخت', 'سفر', 'هوا', 'نان', 'میز', 'پنجره', 'دفتر', 'خیابان',
              'باغ', 'ماهی', 'شهر', 'رود', 'اتاق', 'کفش', 'لباس', 'میوه', 'سبزی', 'آسمان',
              'کوه', 'دشت', 'برف', 'باران', 'دوچرخه', 'قطار', 'فرودگاه', 'رستوران', 'پول',
              'خنده', 'بازی', 'قصه', 'شعر', 'موسیقی', 'رنگ', 'کاغذ', 'مداد', 'تخته', 'کلاس']
CONTROL_EN = ['book', 'school', 'tree', 'trip', 'air', 'bread', 'table', 'window', 'office',
              'street', 'garden', 'fish', 'city', 'river', 'room', 'shoe', 'clothes', 'fruit',
              'sky', 'mountain', 'plain', 'snow', 'rain', 'bicycle', 'train', 'airport',
              'restaurant', 'money', 'laugh', 'game', 'story', 'poem', 'music', 'color',
              'paper', 'pencil', 'board', 'class']


def worker_control(args):
    clip, gram_fa, gram_en, win, hop, min_conf, tmp = args
    return termspot.worker((clip, gram_fa + ['[unk]'], gram_en + ['[unk]'],
                            win, hop, min_conf, tmp))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--clips', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--win', type=float, default=1.8)
    ap.add_argument('--hop', type=float, default=0.9)
    ap.add_argument('--min-conf', type=float, default=0.5)
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--tmp', default='/tmp/termspot')
    ap.add_argument('--out-json', default='')
    a = ap.parse_args()
    Path(a.tmp).mkdir(parents=True, exist_ok=True)
    clips = [c.strip() for c in a.clips.split(',') if c.strip()]

    fa_terms, en_terms = termspot.term_lists()
    res = {}
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for clip, occ_t, nw_t, unk_t in ex.map(termspot.worker,
                                               [(c, fa_terms + ['[unk]'], en_terms + ['[unk]'],
                                                 a.win, a.hop, a.min_conf, a.tmp) for c in clips]):
            res.setdefault(clip, {})['term'] = {'hits': len(occ_t), 'windows': nw_t, 'unk': unk_t,
                                                'confs': [o['conf'] for o in occ_t]}
            res.setdefault(clip, {})['term_occ'] = occ_t
        print('  ✓ گرامر اصطلاح‌ها تمام شد', flush=True)
        for clip, occ_c, nw_c, unk_c in ex.map(worker_control,
                                               [(c, CONTROL_FA, CONTROL_EN, a.win, a.hop,
                                                 a.min_conf, a.tmp) for c in clips]):
            res.setdefault(clip, {})['control'] = {'hits': len(occ_c), 'windows': nw_c, 'unk': unk_c,
                                                   'confs': [o['conf'] for o in occ_c]}
            res.setdefault(clip, {})['control_occ'] = occ_c
        print('  ✓ گرامر کنترل تمام شد', flush=True)

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    lines = ['# سنجشِ توهمِ رمزگشایی اجباری (گرامر اصطلاح ↔ گرامر کنترل)', '',
             '> گرامر کنترل: واژه‌های رایج و بی‌ربط (نان، مدرسه، دوچرخه / table, garden…) با تعداد و',
             '> طول مشابه. اگر دیکود اجباری «توهم» می‌زد، نرخِ hit و اطمینانِ دو گرامر باید نزدیک باشد.', '',
             '| قطعه | پنجره | hit اصطلاح | hit کنترل | unk اصطلاح | unk کنترل | میانگین اطمینان اصطلاح | کنترل |',
             '|---|---|---|---|---|---|---|---|']
    tot = defaultdict(int)
    for clip, d in res.items():
        t, c = d['term'], d['control']
        lines.append(f"| {clip} | {t['windows']} | {t['hits']} | {c['hits']} | {t['unk']} | {c['unk']} | "
                     f"{mean(t['confs'])} | {mean(c['confs'])} |")
        tot['win'] += t['windows']; tot['th'] += t['hits']; tot['ch'] += c['hits']
        tot['tu'] += t['unk']; tot['cu'] += c['unk']
    lines += ['', f"**مجموع:** پنجره {tot['win']} · hit اصطلاح {tot['th']} · hit کنترل {tot['ch']} · "
              f"unk اصطلاح {tot['tu']} · unk کنترل {tot['cu']}", '']
    lines.append(f"- نرخِ hit با گرامر اصطلاح: **{tot['th']/max(1,tot['win']):.2f}** به‌ازای هر پنجره "
                 f"(کنترل: {tot['ch']/max(1,tot['win']):.2f})")
    lines.append(f"- نرخِ ردِ صریح (unk): با اصطلاح **{tot['tu']/max(1,tot['win']):.2f}** · "
                 f"کنترل **{tot['cu']/max(1,tot['win']):.2f}**")
    Path(a.out).write_text('\n'.join(lines), encoding='utf-8')
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
        print(f'   رخدادها → {a.out_json}')
    print(f'✓ {a.out}')
    print(f"   hit اصطلاح {tot['th']} vs کنترل {tot['ch']} در {tot['win']} پنجره")


if __name__ == '__main__':
    main()
