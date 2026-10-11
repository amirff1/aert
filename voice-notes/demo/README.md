# نمونهٔ خروجی — پیاده‌سازی صدای ویدیوی موجود در مخزن

فایل ورودی: `3fb216wwwwwwwwwwwwwqb8-a1c5-4977-92be-eb36a5f367a6.mp4`
(۳۹٬۷ ثانیه، ویدیو 1080p + صدای AAC استریو 44.1kHz)

| ویژگی | مقدار |
|---|---|
| زبان تشخیص‌داده‌شده (خودکار) | **انگلیسی** — اطمینان ۹۷٪ |
| ماهیت صدا | گفتار انگیزشی/تبلیغاتی روی موسیقی پس‌زمینه |
| موتورهای آزمایش‌شده | Whisper-tiny (ONNX + beam-search)، whisper.cpp (ggml-tiny)، Vosk-en |

## فایل‌ها

| فایل | توضیح |
|---|---|
| `mp4-transcript-onnx.txt` | متن پیاده‌شده با موتور ONNX (تمیزترین خروجی — پیشنهادی) |
| `mp4-transcript-whisper.txt` / `.srt` / `.json` | خروجی whisper.cpp با زمان‌بندی جمله‌ها (زیرنویس SRT) |
| `mp4-transcript-vosk.txt` | خروجی Vosk انگلیسی |
| `joze.md` / `joze.html` | جزوهٔ ساخته‌شده از همین صدا (نمونهٔ خودکار) |

## متن پیاده‌شده (بازبینی‌شدهٔ انسانی)

> Might not feel like it, but these are your glory days — the **salad days**, you know?
> Nothing is going to beat who you are now.
> You can't see all the fucked-up shit that's looming on the horizon.
> Enjoy this, dude. This right now is all that there is. All the time.
> You would be perfect… trust me.

نکته‌ها:
* عبارت «salad days» یک اصطلاح انگلیسی به‌معنی «روزهای طلایی جوانی» است؛ مدل‌های کوچک آن را «salad gears / a salad years» شنیده بودند.
* «looming» در برخی خروجی‌ها «lumen / aluminum» شنیده شده — نشانهٔ اثر موسیقی پس‌زمینه بر دقت است.
* تگ‌های `[MUSIC PLAYING]` را ابزار به‌صورت خودکار از متن نهایی حذف می‌کند.

## ترجمهٔ محتوا (فارسی)

> ممکن است حسش نکنی، اما این‌ها همان روزهای طلایی تو هستند — روزهای جوانی، می‌دانی؟
> هیچ‌چیز به‌اندازهٔ «آن‌که همین حالا هستی» خوب نخواهد بود.
> تو نمی‌توانی آن همه چیزهای به‌هم‌ریخته‌ای را که در افق در راه‌اند ببینی.
> از همین حالا لذت ببر رفیق؛ همین لحظه تمام دارایی توست — همیشه.
> تو فوق‌العاده خواهی بود… به من اعتماد کن.

## بازتولید این خروجی

```bash
# داخل پوشهٔ ریشهٔ مخزن:
bash voice-notes/setup.sh                      # نصب محیط + واکشی مدل‌ها (یک‌بار)
~/asr-venv/bin/python voice-notes/transcribe.py \
    3fb216wwwwwwwwwwwwwqb8-a1c5-4977-92be-eb36a5f367a6.mp4 \
    --engine onnx --out out
~/asr-venv/bin/python voice-notes/make_joze.py \
    --transcript out/3fb216wwwwwwwwwwwwwqb8-a1c5-4977-92be-eb36a5f367a6.json \
    --title "جزوهٔ صوتی" --out out
```
