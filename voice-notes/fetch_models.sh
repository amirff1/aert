#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  واکشی مدل‌های تشخیص گفتار (بدون وابستگی به سرورهای بسته)
# ---------------------------------------------------------------------------
#  این اسکریپت مدل‌ها را از منابعی می‌گیرد که در سندباکس قابل‌دسترس‌اند:
#    ۱) ggml-tiny.bin                     ← مخزن گیت‌هاب (blob واقعی، بدون LFS)
#    ۲) vosk-model-small-en-us-0.15.zip   ← مخزن گیت‌هاب (blob واقعی)
#    ۳) vosk-model-small-fa-0.42          ← مخزن گیت‌هاب (فارسی)
#    ۴) whisper-tiny.onnx (beam-search)   ← رجیستری npm
#  مدل‌ها بیرون از مخزن گیت ذخیره می‌شوند (پیش‌فرض: ~/asr-models).
# ---------------------------------------------------------------------------
set -euo pipefail

MODELS_DIR="${ASR_MODELS_DIR:-$HOME/asr-models}"
WORK="${ASR_WORK_DIR:-$HOME/.cache/asr-fetch}"
mkdir -p "$MODELS_DIR/models" "$MODELS_DIR/vosk-en" "$MODELS_DIR/whisper-onnx" "$WORK"

clone_blob() {   # $1=repo  $2=path-in-repo  $3=dest  $4=name
  local repo="$1" path="$2" dest="$3" name="$4"
  local dir="$WORK/$name"
  rm -rf "$dir"
  echo "→ $name از $repo"
  git clone --quiet --filter=blob:none --no-checkout --depth 1 "https://github.com/$repo" "$dir"
  git -C "$dir" sparse-checkout set --no-cone "$path"
  git -C "$dir" checkout --quiet
  cp -f "$dir/$path" "$dest"
  ls -la "$dest"
}

# ---------------------------------------------------------------- ۱) whisper ggml-tiny
if [ -s "$MODELS_DIR/models/ggml-tiny.bin" ]; then
  echo "✓ ggml-tiny.bin موجود است"
else
  clone_blob antem0613/DesktopAgent Assets/StreamingAssets/Whisper/ggml-tiny.bin \
             "$MODELS_DIR/models/ggml-tiny.bin" tiny
fi

# ---------------------------------------------------------------- ۲) vosk (انگلیسی)
if [ -d "$MODELS_DIR/vosk-en/vosk-model-small-en-us-0.15" ]; then
  echo "✓ مدل Vosk موجود است"
else
  clone_blob arkadeepnag/limelight server/services/vosk-model-small-en-us-0.15.zip \
             "$WORK/vosk.zip" vosk
  python3 - "$WORK/vosk.zip" "$MODELS_DIR/vosk-en" <<'PY'
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
print("✓ استخراج شد →", sys.argv[2])
PY
fi

# ---------------------------------------------------------------- ۳) vosk فارسی
if [ -d "$MODELS_DIR/vosk-fa/vosk-model-small-fa-0.42" ]; then
  echo "✓ مدل Vosk فارسی موجود است"
else
  echo "→ مدل Vosk فارسی از omid3098/Parspeak"
  rm -rf "$WORK/fa"
  git clone --quiet --filter=blob:none --no-checkout --depth 1 \
      https://github.com/omid3098/Parspeak "$WORK/fa"
  git -C "$WORK/fa" sparse-checkout set --no-cone models
  git -C "$WORK/fa" checkout --quiet
  mkdir -p "$MODELS_DIR/vosk-fa"
  cp -r "$WORK/fa/models/vosk-model-small-fa-0.42" "$MODELS_DIR/vosk-fa/"
  du -sh "$MODELS_DIR/vosk-fa"
fi

# ---------------------------------------------------------------- ۴) whisper ONNX
if [ -s "$MODELS_DIR/whisper-onnx/whisper_cpu_int8_0_model.onnx" ]; then
  echo "✓ مدل ONNX موجود است"
else
  echo "→ whisper-tiny ONNX از رجیستری npm"
  curl -sSL --retry 3 -o "$WORK/onnx.tgz" \
    "https://registry.npmjs.org/speech-transcriber/-/speech-transcriber-1.0.0.tgz"
  tar -xzf "$WORK/onnx.tgz" -C "$WORK" package/dist/model
  cp -f "$WORK/package/dist/model/whisper_cpu_int8_0_model.onnx" \
        "$MODELS_DIR/whisper-onnx/whisper_cpu_int8_0_model.onnx"
  ls -la "$MODELS_DIR/whisper-onnx/"
fi

# ------------------------------------------------- ۵) Hush / DeepFilterNet3 (ONNX)
# مدل‌های نویزگیری عصبیِ DF3 (آموزش‌دیدهٔ Meta). فایل‌های ONNX فقط با clone فیلترشده
# قابل دریافت‌اند (raw.githubusercontent و release-assets در این محیط مسدودند).
HUSH_DIR="${HUSH_DIR:-/home/user/.cache/hush}"
if [ -s "$HUSH_DIR/onnx/enc.onnx" ] && [ -s "$HUSH_DIR/onnx/df_dec.onnx" ]; then
  echo "✓ مدل‌های Hush موجودند در $HUSH_DIR/onnx"
else
  echo "→ دریافت مدل‌های Hush (DF3 ONNX ~۸.۸MB)"
  rm -rf "$HUSH_DIR"
  git clone --quiet --filter=blob:none --no-checkout --depth 1 \
      https://github.com/mah92/hush_cpp "$HUSH_DIR"
  git -C "$HUSH_DIR" sparse-checkout set --no-cone onnx src
  git -C "$HUSH_DIR" checkout --quiet
  ls -la "$HUSH_DIR/onnx"
fi

echo
echo "✓ همهٔ مدل‌ها آماده‌اند در: $MODELS_DIR"
du -sh "$MODELS_DIR"/* 2>/dev/null || true
