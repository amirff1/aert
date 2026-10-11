#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
صدا → متن  (Offline ASR toolkit)
=================================
سه موتور بدون اینترنت:
  * onnx    : Whisper-tiny (ONNX + beam-search)  → تمیزترین متن انگلیسی
  * whisper : whisper.cpp (ggml)                  → چندزبانه + زمان‌بندی دقیق (SRT)
  * vosk    : Vosk small-en-us                    → انگلیسی با زمان کلمات

استفاده:
    python3 transcribe.py INPUT [--engine auto|onnx|whisper|vosk] [--language fa|en|auto]
                              [--out DIR] [--formats txt,srt,json,md]

INPUT می‌تواند هر فایل صوتی/ویدیویی باشد (mp3, wav, m4a, mp4, mov, ogg, flac, webm …)
یا یک فایل PowerPoint / zip که صدا داخلش است.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MODELS_DIR = Path(os.environ.get("ASR_MODELS_DIR", str(Path.home() / "asr-models")))
MEDIA_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac|wma|mp4|mov|mkv|webm|avi|wmv|m4v)$", re.I)
AUDIO_ONLY_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac|wma)$", re.I)


# ---------------------------------------------------------------- helpers
def die(msg: str) -> "None":
    print("خطا: " + msg, file=sys.stderr)
    sys.exit(1)


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        die("ffmpeg پیدا نشد. نصب:  pip install imageio-ffmpeg")


def to_wav(src: Path, dst: Path, sr: int = 16000, denoise: bool = False) -> Path:
    """هر فرمتی → wav مونو 16kHz PCM16 (اختیاری: نویزگیری + نرمال‌سازی)"""
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
    if denoise:
        cmd += ["-af", "afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)]
    subprocess.run(cmd, check=True)
    return dst


def fmt_ts(t: float, srt: bool = False) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if srt:
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def model_path(name: str, *candidates: str) -> Path | None:
    for c in candidates:
        p = MODELS_DIR / c
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------- engines
def transcribe_onnx(wav: Path, language_hint: str | None = None, beams: int = 5,
                    chunk_seconds: int = 30, overlap: float = 0.0) -> list[dict]:
    """Whisper-tiny ONNX (audio_pcm → str) با beam search. چانک ۳۰ ثانیه‌ای."""
    import numpy as np
    import soundfile as sf
    import onnxruntime as ort
    import onnxruntime_extensions  # noqa: F401  (custom ops لازم است)

    p = model_path("whisper-onnx", "whisper-onnx/package/dist/model/whisper_cpu_int8_0_model.onnx",
                   "whisper-onnx/whisper_cpu_int8_0_model.onnx")
    if p is None:
        die(f"مدل ONNX پیدا نشد (زیر {MODELS_DIR}/whisper-onnx). اول fetch_models.sh را اجرا کنید.")

    so = ort.SessionOptions()
    so.register_custom_ops_library(onnxruntime_extensions.get_library_path())
    sess = ort.InferenceSession(str(p), so, providers=["CPUExecutionProvider"])

    x, sr = sf.read(str(wav), dtype="float32")
    if sr != 16000:
        die("wav ورودی باید 16kHz باشد (از to_wav استفاده کنید)")
    if x.ndim > 1:
        x = x.mean(axis=1)

    n = int(16000 * chunk_seconds)
    step = int(n * (1.0 - overlap)) or n
    segs: list[dict] = []
    for start in range(0, max(len(x), 1), step):
        chunk = x[start:start + n]
        if len(chunk) < 1600:            # کمتر از ۰٬۱ ثانیه
            break
        if len(chunk) < n:               # پد کردن تا ۳۰ ثانیه
            import numpy as np
            chunk = np.pad(chunk, (0, n - len(chunk)))
        outs = sess.run(None, {
            "audio_pcm": chunk.reshape(1, -1).astype("float32"),
            "max_length": [448], "min_length": [1], "num_beams": [beams],
            "num_return_sequences": [1], "length_penalty": [1.0], "repetition_penalty": [1.0],
        })
        txt = str(outs[0][0][0]).strip()
        txt = re.sub(r"\[(MUSIC|SOUND|BLANK_AUDIO|Applause|Laughter)[^\]]*\]", " ", txt, flags=re.I)
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            segs.append({
                "t0": start / 16000.0,
                "t1": min(len(x), start + n) / 16000.0,
                "text": txt,
                "engine": "whisper-tiny-onnx(beam)",
            })
    return segs


def transcribe_whisper(wav: Path, language: str | None = None, threads: int = 2,
                       initial_prompt: str | None = None) -> list[dict]:
    """whisper.cpp (pywhispercpp) با مدل ggml."""
    from pywhispercpp.model import Model

    p = model_path("whisper", "models/ggml-tiny.bin", "ggml-tiny.bin")
    if p is None:
        die(f"مدل ggml پیدا نشد (زیر {MODELS_DIR}/models). اول fetch_models.sh را اجرا کنید.")

    kw = {}
    if initial_prompt:
        kw["initial_prompt"] = initial_prompt
    m = Model(str(p), n_threads=threads, print_realtime=False, print_progress=False,
              language=(language or "auto"), translate=False)
    segs: list[dict] = []
    for s in m.transcribe(str(wav), language=(language or None), **kw):
        segs.append({
            "t0": s.t0 / 100.0, "t1": s.t1 / 100.0,
            "text": s.text.strip(), "engine": "whisper.cpp",
        })
    return segs


def transcribe_vosk(wav: Path, persian: bool = False) -> list[dict]:
    """Vosk (Kaldi) — انگلیسی یا فارسی."""
    import wave as _w
    from vosk import Model, KaldiRecognizer, SetLogLevel

    if persian:
        d = model_path("vosk-fa", "vosk-fa/vosk-model-small-fa-0.42", "vosk-fa2",
                            "vosk-model-small-fa-0.42", "vosk-model-small-fa-0.5")
    else:
        d = model_path("vosk-en", "vosk-en/vosk-model-small-en-us-0.15", "vosk-model-small-en-us-0.15")
    if d is None:
        die(f"مدل Vosk پیدا نشد (زیر {MODELS_DIR}/{'vosk-fa' if persian else 'vosk-en'}). "
            "اول fetch_models.sh را اجرا کنید.")

    SetLogLevel(-1)
    m = Model(str(d))
    wf = _w.open(str(wav), "rb")
    rec = KaldiRecognizer(m, wf.getframerate())
    rec.SetWords(True)
    segs: list[dict] = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            r = json.loads(rec.Result())
            if r.get("text"):
                ws = r.get("result") or []
                segs.append({"t0": ws[0]["start"] if ws else 0.0,
                             "t1": ws[-1]["end"] if ws else 0.0,
                             "text": r["text"], "engine": "vosk-fa" if persian else "vosk-en"})
    r = json.loads(rec.FinalResult())
    if r.get("text"):
        ws = r.get("result") or []
        segs.append({"t0": ws[0]["start"] if ws else 0.0,
                     "t1": ws[-1]["end"] if ws else 0.0,
                     "text": r["text"], "engine": "vosk-fa" if persian else "vosk-en"})
    return segs


# ---------------------------------------------------------------- writers
def write_outputs(segs: list[dict], out_dir: Path, stem: str, formats: set[str]) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    full_text = " ".join(s["text"] for s in segs).strip()
    if "txt" in formats:
        p = out_dir / f"{stem}.txt"
        p.write_text(full_text + "\n", encoding="utf-8")
        written["txt"] = p
    if "srt" in formats:
        lines = []
        for i, s in enumerate(segs, 1):
            lines += [str(i), f"{fmt_ts(s['t0'], True)} --> {fmt_ts(s['t1'], True)}", s["text"], ""]
        p = out_dir / f"{stem}.srt"
        p.write_text("\n".join(lines), encoding="utf-8")
        written["srt"] = p
    if "json" in formats:
        p = out_dir / f"{stem}.json"
        p.write_text(json.dumps({"segments": segs, "text": full_text},
                                ensure_ascii=False, indent=2), encoding="utf-8")
        written["json"] = p
    if "md" in formats:
        p = out_dir / f"{stem}.md"
        body = "\n".join(f"- `{fmt_ts(s['t0'])}` {s['text']}" for s in segs)
        p.write_text(f"# متن پیاده‌شده — {stem}\n\n{body}\n", encoding="utf-8")
        written["md"] = p
    return written


# ---------------------------------------------------------------- pptx / zip
def extract_pptx_media(path: Path, work: Path) -> list[Path]:
    """صدا/ویدیوهای جاسازی‌شده در pptx (یا هر zip) را بیرون می‌کشد."""
    import zipfile
    media: list[Path] = []
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if "/media/" in name or name.startswith("ppt/media/"):
                if MEDIA_RE.search(name):
                    dst = work / Path(name).name
                    i = 1
                    while dst.exists():
                        dst = work / f"{Path(name).stem}_{i}{Path(name).suffix}"
                        i += 1
                    with z.open(name) as src, open(dst, "wb") as fh:
                        shutil.copyfileobj(src, fh)
                    media.append(dst)
    return sorted(media, key=lambda p: p.name)


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="صدا به متن (offline)")
    ap.add_argument("input", help="فایل صوتی/ویدیویی یا pptx/zip")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "onnx", "whisper", "vosk", "vosk-fa"])
    ap.add_argument("--denoise", action="store_true", help="نویزگیری و نرمال‌سازی صدا پیش از تشخیص")
    ap.add_argument("--language", default=None, help="fa | en | … (پیش‌فرض: تشخیص خودکار)")
    ap.add_argument("--out", default="out", help="پوشهٔ خروجی")
    ap.add_argument("--formats", default="txt,srt,json,md")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--beams", type=int, default=5)
    ap.add_argument("--prompt", default=None,
                    help="راهنمای متنی برای موتور whisper (بهبود لحن/واژگان، مثلاً یک جملهٔ فارسی)")
    ap.add_argument("--raw", action="store_true", help="بدون پاک‌سازی متن")
    args = ap.parse_args()

    src = Path(args.input).expanduser()
    if not src.exists():
        die(f"فایل پیدا نشد: {src}")
    out_dir = Path(args.out).expanduser()
    formats = {f.strip() for f in args.formats.split(",") if f.strip()}

    # انتخاب موتور
    engine = args.engine
    if engine == "auto":
        if args.language and args.language.lower().startswith("fa"):
            engine = "vosk-fa" if (MODELS_DIR / "vosk-fa").exists() else "whisper"
        elif args.language and args.language.lower() not in ("en", "auto"):
            engine = "whisper"
        elif (MODELS_DIR / "whisper-onnx").exists():
            engine = "onnx"             # best English text
        else:
            engine = "whisper"
    print(f"→ موتور: {engine}" + (f" | زبان: {args.language}" if args.language else ""))

    work = Path(tempfile.mkdtemp(prefix="asr-"))
    all_written: dict[str, dict[str, Path]] = {}

    if src.suffix.lower() in (".pptx", ".zip"):
        from pptx_extract import extract_pptx  # type: ignore
        print("→ استخراج محتوای پاورپوینت (اسلایدها، نُت‌ها، مدیا) …")
        info = extract_pptx(src, out_dir / "slides")
        media = extract_pptx_media(src, work / "media")
        print(f"   {len(info['slides'])} اسلاید، {len(media)} فایل صوتی/ویدیویی")
        for i, mfile in enumerate(media, 1):
            print(f"→ [{i}/{len(media)}] {mfile.name}")
            wav = to_wav(mfile, work / f"m{i}.wav", denoise=args.denoise)
            segs = run_engine(engine, wav, args)
            stem = f"{src.stem}-media{i}"
            all_written[stem] = write_outputs(segs, out_dir, stem, formats)
            print(f"   {len(segs)} قطعه، {sum(len(s['text']) for s in segs)} کاراکتر")
        print(f"\n✓ اسلایدها: {out_dir/'slides'/'slides.md'}")
    else:
        wav = to_wav(src, work / "audio.wav", denoise=args.denoise)
        segs = run_engine(engine, wav, args)
        stem = src.stem
        all_written[stem] = write_outputs(segs, out_dir, stem, formats)
        print(f"✓ {len(segs)} قطعه، {sum(len(s['text']) for s in segs)} کاراکتر")
        text = " ".join(s["text"] for s in segs)
        print("\n--- متن ---")
        print(text[:1200] + ("…" if len(text) > 1200 else ""))
        if len(segs) and segs[0].get("engine", "").startswith("whisper-tiny-onnx"):
            print("\nنکته: زمان‌بندی برای موتور onnx تقریبی است (پنجره‌های ۳۰ ثانیه‌ای).")

    for stem, files in all_written.items():
        for fmt, p in files.items():
            print(f"  {fmt:4s} → {p}")
    shutil.rmtree(work, ignore_errors=True)


def run_engine(engine: str, wav: Path, args) -> list[dict]:
    if engine == "onnx":
        return transcribe_onnx(wav, args.language, beams=args.beams)
    if engine == "vosk":
        return transcribe_vosk(wav, persian=False)
    if engine == "vosk-fa":
        return transcribe_vosk(wav, persian=True)
    return transcribe_whisper(wav, args.language, threads=args.threads,
                              initial_prompt=getattr(args, "prompt", None))


if __name__ == "__main__":
    main()
