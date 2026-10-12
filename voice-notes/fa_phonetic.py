#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fa_phonetic — تطبیق آوایی واژگان تخصصی فارسی/انگلیسی
===================================================
سه سرویس:
  ۱) `fa_key(word)`  : کلید آوایی فارسی (یکسان‌سازی حروف هم‌صدا: س/ص/ث، ز/ذ/ض/ظ، ت/ط، ق/غ …)
  ۲) `en_key(word)`  : کلید آوایی انگلیسی (Soundex-مانند: ph→f، c→k، حذف واکه‌ها …)
  ۳) `snap_words()` : روی خروجی رأی‌گیری، واژه‌های کم‌اطمینان را به نزدیک‌ترین
                      «واژهٔ تخصصی دامنه» می‌چسباند — اگر شباهت آوایی قوی باشد.
                     هم‌چنین عبارت‌های چندواژه‌ای انگلیسی (fragmented QRS،
                     transition zone …) با «اسکلت آوایی» بازشناسی می‌شوند.
"""
from __future__ import annotations
import json, re
from pathlib import Path

# ------------------------------------------------------------------ کلید آوایی فارسی
_FA_MAP = {}
for group, rep in {
    'سصث': 'س', 'زذضظ': 'ز', 'تط': 'ت', 'قغ': 'ق', 'هح': 'ه', 'کك': 'ک',
    'ا آ أ إ ٱ': 'ا', 'یيىئ': 'ی', 'وؤ': 'و', 'ن': 'ن', 'م': 'م',
}.items():
    for ch in group:
        if ch != ' ':
            _FA_MAP[ch] = rep
_FA_MAP.update({'ة': 'ه', 'ۀ': 'ه', 'ء': '', 'ع': '', 'ژ': 'ژ', 'چ': 'چ',
                'پ': 'پ', 'گ': 'گ', 'ب': 'ب', 'د': 'د', 'ر': 'ر', 'ف': 'ف',
                'ل': 'ل', 'ش': 'ش', 'خ': 'خ', 'ج': 'ج', 'ه': 'ه', 'ی': 'ی',
                'و': 'و', 'ا': 'ا', 'ت': 'ت', 'ن': 'ن', 'م': 'م', 'ک': 'ک',
                'س': 'س', 'ز': 'ز', 'ق': 'ق', 'ث': 'س', 'ص': 'س', 'ض': 'ز',
                'ط': 'ت', 'ظ': 'ز', 'ذ': 'ز', 'غ': 'ق'})


def fa_key(w: str) -> str:
    """کلید آوایی فارسی — حروف هم‌صدا یکسان، واکه‌های کوتاه حذف"""
    w = re.sub(r'[\u064B-\u0652\u200c\u200f\u200e]', '', w.strip())
    w = ''.join(_FA_MAP.get(c, '') for c in w)
    # حذف واکه‌های ناپایدار (ا/و/ی) مگر در جایگاه اول و آخر برای کشف اسکلت
    core = w[1:-1] if len(w) > 3 else w
    core = re.sub(r'[اوی]', '', core) or w
    return (w[:1] + core + w[-1:]) if len(w) > 3 else w


_EN_MAP = {'ph': 'f', 'ck': 'k', 'cq': 'k', 'qu': 'k', 'x': 'ks', 'q': 'k',
           'c': 'k', 'w': 'v', 'z': 's', 'y': 'i', 'j': 'i', 'sch': 's', 'ch': 's',
           'th': 't', 'gh': 'g', 'sh': 's', 'll': 'l', 'ss': 's', 'tt': 't'}


def en_key(w: str) -> str:
    """کلید آوایی انگلیسی (تقریبی، Soundex-مانند)"""
    w = re.sub(r'[^a-z]', '', w.lower())
    for k in ('sch', 'ph', 'sh', 'ch', 'th', 'gh'):
        w = w.replace(k, _EN_MAP.get(k, k))
    for ch in 'xyzwqjc':
        w = w.replace(ch, _EN_MAP.get(ch, ch))
    if not w:
        return ''
    first, rest = w[0], re.sub(r'[aeiou]', '', w[1:])
    return (first + rest)[:8]


def edit1(a: str, b: str) -> bool:
    """فاصلهٔ ویرایشی ≤ ۱"""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    diff = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            diff += 1
            if diff > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return True


# --------------------------------------------------- واژگان تخصصی: انگلیسی → فارسیِ گفته‌شده
TERMS: list[dict] = [
    # (انگلیسی، تلفظ‌های فارسی رایج در کلاس)
    {'en': 'QRS', 'fa': ['کیو آر اس', 'کیارس', 'کیوآراس', 'کی آر اس', 'قورس']},
    {'en': 'PR', 'fa': ['پی آر', 'پیر', 'پیار']},
    {'en': 'ST', 'fa': ['اس تی', 'استی']},
    {'en': 'QT', 'fa': ['کیو تی', 'کیوتی']},
    {'en': 'MI', 'fa': ['ام آی', 'آرای ام آی', 'ام‌آی']},
    {'en': 'WPW', 'fa': ['دبلیو پی دبلیو']},
    {'en': 'axis', 'fa': ['اکسیس', 'عکسی', 'عکس', 'اکسی']},
    {'en': 'scale', 'fa': ['اسکیل', 'اسکله', 'اسکل', 'اسکیل‌']},
    {'en': 'speed', 'fa': ['اسپید', 'اسپیده', 'اسپیید']},
    {'en': 'gain', 'fa': ['گین', 'گریم', 'گنگ', 'گنت', 'جین']},
    {'en': 'millivolt', 'fa': ['میلی ولت', 'میلی‌ولت', 'میلی وات', 'میلیون وات']},
    {'en': 'calibration', 'fa': ['کالیبراسیون', 'کالیبره']},
    {'en': 'delta wave', 'fa': ['موج دلتا', 'دلتا']},
    {'en': 'transition zone', 'fa': ['ترنزیشن زون', 'زون', 'ناحیه گذر']},
    {'en': 'R progression', 'fa': ['آر پروگرشن', 'پیشرفت آر', 'پروگرشن']},
    {'en': 'fragmented QRS', 'fa': ['فرگمنتد کیو آر اس', 'فرگمنت']},
    {'en': 'bundle branch block', 'fa': ['باندل برانچ بلاک', 'باندل', 'برانچ']},
    {'en': 'left/right bundle', 'fa': ['لفت باندل', 'رایت باندل']},
    {'en': 'fascicular', 'fa': ['فاسیکولار']},
    {'en': 'ischemia', 'fa': ['ایسکمی', 'اسکیمی', 'ایسکمیا']},
    {'en': 'infarction', 'fa': ['انفارکتوس', 'انفارکشن', 'اینفارکت']},
    {'en': 'arrhythmia', 'fa': ['آریتمی', 'آریتمیا', 'اریتمی']},
    {'en': 'bradycardia', 'fa': ['برادی‌کاردی', 'برادیکاردی']},
    {'en': 'tachycardia', 'fa': ['تاکی‌کاردی', 'تاکی کاردی', 'تاکی‌کاردیا']},
    {'en': 'hypertrophy', 'fa': ['هایپرتروفی', 'هیپرتروفی', 'هایپرتروفیا']},
    {'en': 'pulmonary', 'fa': ['پولمونر', 'پولموناری']},
    {'en': 'mitral', 'fa': ['میترال', 'میتراله']},
    {'en': 'electrode', 'fa': ['الکترود', 'الکترودی']},
    {'en': 'depolarization', 'fa': ['دپولاریزاسیون', 'دیپولاریزاسیون', 'دپلاریزاسیون']},
    {'en': 'repolarization', 'fa': ['رپولاریزاسیون', 'ریپولاریزاسیون']},
    {'en': 'isoelectric', 'fa': ['ایزوالکتریک', 'ایزو الکتریک', 'ایزومتریک']},
    {'en': 'septum', 'fa': ['سپتوم', 'سپتوم‌']},
    {'en': 'precordial', 'fa': ['پره‌کوردیال', 'پریکوردیال', 'پرخوری']},
    {'en': 'limb leads', 'fa': ['لیمب لید', 'لیدهای اندامی']},
    {'en': 'sinus', 'fa': ['سینوس', 'سینوسی']},
    {'en': 'node', 'fa': ['نود', 'گره']},
    {'en': 'inferior', 'fa': ['اینفریور', 'تحتانی']},
    {'en': 'anterior', 'fa': ['آنتریور', 'قدامی']},
    {'en': 'lateral', 'fa': ['لاترال', 'لترال']},
    {'en': 'contiguous', 'fa': ['کانتیگیوس', 'همجوار']},
    {'en': 'hyperkalemia', 'fa': ['هیپرکالمی', 'هایپرکالمیا']},
    {'en': 'hypokalemia', 'fa': ['هیپوکالمی', 'هایپوکالمیا']},
    {'en': 'Sokolow', 'fa': ['سوکولو', 'سوکالو']},
    {'en': 'amplitude', 'fa': ['آمپلی‌تود', 'آمپلیتود', 'آمپلی تود']},
    {'en': 'voltage', 'fa': ['ولتاژ', 'ولتااز']},
    {'en': 'interval', 'fa': ['اینتروال', 'فاصله']},
    {'en': 'segment', 'fa': ['سگمنت', 'سیگمنت']},
    {'en': 'wave', 'fa': ['ویو', 'موج']},
    {'en': 'block', 'fa': ['بلاک', 'بلوک']},
    {'en': 'normal', 'fa': ['نرمال', 'نورمال']},
    {'en': 'deviation', 'fa': ['دوییشن', 'انحراف']},
    {'en': 'paper', 'fa': ['پیپر', 'کاغذ']},
    {'en': 'signal', 'fa': ['سیگنال']},
    {'en': 'artifact', 'fa': ['آرتیفکت']},
    {'en': 'monitor', 'fa': ['مانیتور']},
    {'en': 'standard', 'fa': ['استاندارد']},
    {'en': 'diagnosis', 'fa': ['دیگنوسیس', 'دیگنوز']},
    {'en': 'positive/negative', 'fa': ['پوزیتیو', 'نگتیو']},
]


class Lexicon:
    """فرهنگ واژگان دامنه با کلیدهای آوایی فارسی و انگلیسی"""

    def __init__(self, extra_persian: list[str] | None = None, extra_english: list[str] | None = None):
        self.fa2en: dict[str, str] = {}
        self.exact: dict[str, str] = {}            # شکل دقیقِ واژه → واژهٔ canonical
        self.fa_terms: dict[str, set[str]] = {}    # کلید آوایی → {واژه‌های کاندید}
        for t in TERMS:
            for form in [t['en']] + t['fa']:
                self.exact[form] = t['en']
                k = fa_key(form)
                if len(k) >= 2:
                    self.fa_terms.setdefault(k, set()).add(t['en'])
        for w in (extra_persian or []):
            self.exact.setdefault(w, w)
            self.fa_terms.setdefault(fa_key(w), set()).add(w)
        self.en_terms = {en_key(t['en']): t['en'] for t in TERMS}
        for w in (extra_english or []):
            self.en_terms.setdefault(en_key(w), w)
        self.multi = [t for t in TERMS if ' ' in t['en'] or len(t['fa'][0].split()) > 1]

    # ------------------------------------------------------------------
    def best_persian(self, word: str, min_len: int = 3) -> tuple[str, str] | None:
        """نزدیک‌ترین واژهٔ دامنه؛ فقط اگر **بی‌ابهام** باشد.
        (کلید آوایی به‌تنهایی مبهم باشد → None؛ شکل دقیقِ واژه همیشه پذیرفته می‌شود.)"""
        w = word.strip()
        if w in self.exact:
            return w, self.exact[w]
        k = fa_key(w)
        if len(k) < min_len:
            return None
        if k in self.fa_terms:
            cand = self.fa_terms[k]
            return (k, next(iter(cand))) if len(cand) == 1 else None
        hits = {en for cand, ens in self.fa_terms.items()
                if abs(len(cand) - len(k)) <= 1 and edit1(cand, k) for en in ens}
        return (k, next(iter(hits))) if len(hits) == 1 else None

    def best_english(self, word: str) -> tuple[str, str] | None:
        k = en_key(word)
        if len(k) < 3:
            return None
        if k in self.en_terms:
            return k, self.en_terms[k]
        for cand, en in self.en_terms.items():
            if edit1(cand, k):
                return cand, en
        return None


def build_default() -> Lexicon:
    """ساخت فرهنگ از فایل واژگان دامنه (اگر موجود باشد)"""
    extra_fa, extra_en = [], []
    for p in [Path('/home/user/work/zadkamali/domain_terms.json'),
              Path('/home/user/aert/voice-notes/zadkamali/domain_terms.json')]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
                items = data if isinstance(data, list) else list(data)
                for it in items:
                    if not isinstance(it, str):
                        continue
                    if re.search(r'[\u0600-\u06FF]', it):
                        extra_fa.append(it)
                    else:
                        extra_en.append(it)
            except Exception:
                pass
            break
    return Lexicon(extra_fa, extra_en)


if __name__ == '__main__':
    L = build_default()
    tests = ['کیارس', 'اسکیل', 'عکسی', 'گریم', 'ولتااز', 'دکودا', 'هیجی راک',
             'فرگمنتد', 'سوکولو', 'پرخوری', 'مچازی', 'شارژی']
    print(f'واژگان: {len(L.fa_terms)} کلید فارسی · {len(L.en_terms)} کلید انگلیسی')
    for t in tests:
        r = L.best_persian(t)
        print(f'  {t:12s} → {r[1] if r else "—"}   (کلید {fa_key(t)})')
    for t in ['kuars', 'scale', 'axis', 'gayn', 'fragmented', 'sokolov']:
        r = L.best_english(t)
        print(f'  EN {t:12s} → {r[1] if r else "—"}   (کلید {en_key(t)})')


class Suggestor:
    """پیشنهاد واژهٔ تخصصی با دروازهٔ «کم‌بسامدی» (علیه شبیه‌های رایج فارسی)

    قاعده:
      • شکل دقیقِ واژه در فرهنگ دامنه → همیشه پذیرفته (ترجمهٔ رسمی، مثل «سینوسی»)
      • تطبیق آوایی — فقط اگر واژه در پیکرهٔ گفتار **کم‌بسامد** باشد
        (zipf(فارسی) < 3.0 و تعداد تکرار در همین پیکره ≤ 2)
      • اگر کلید به چند اصطلاح بخورد (مبهم) → رد
    """

    def __init__(self, corpus_words: list[str] | None = None):
        self.lex = build_default()
        self.count: dict[str, int] = {}
        for w in (corpus_words or []):
            self.count[w] = self.count.get(w, 0) + 1
        try:
            from wordfreq import zipf_frequency
            self.zipf = zipf_frequency
        except Exception:                                    # pragma: no cover
            self.zipf = lambda w, l: 9.0

    def suggest(self, word: str, max_zipf: float = 3.0) -> tuple[str, str] | None:
        """→ (واژهٔ تخصصی، دلیل) یا None"""
        w = word.strip()
        if not w:
            return None
        if w in self.lex.exact:
            # واژه‌های بسیار پُرکاربردِ فارسی (مثل «موج»، «عکس») را پیشنهاد نمی‌کنیم
            if self.zipf(w, 'fa') >= 4.6 and self.count.get(w, 0) > 5:
                return None
            return self.lex.exact[w], 'شکل دقیقِ واژه در واژگان دامنه'
        r = self.lex.best_persian(w)
        if not r:
            return None
        if len(w) < 4:
            return None
        if self.zipf(w, 'fa') >= max_zipf:
            return None
        if self.count.get(w, 0) > 2:
            return None
        return r[1], f'آوایی ≈ {r[1]} (کم‌بسامد در پیکره)'
