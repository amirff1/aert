#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  نصب محیط voice-notes  (پایتون + کتابخانه‌ها + مدل‌ها)
#  استفاده:  bash setup.sh [مسیر-محیط]
# ---------------------------------------------------------------------------
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${1:-$HOME/asr-venv}"

echo "→ ساخت محیط پایتون: $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet \
    numpy soundfile imageio-ffmpeg \
    pywhispercpp vosk python-pptx \
    onnxruntime onnxruntime-extensions

echo "→ بررسی نصب:"
"$VENV/bin/python" - <<'PY'
import importlib
for m in ("numpy", "soundfile", "imageio_ffmpeg", "pywhispercpp", "vosk", "pptx", "onnxruntime"):
    try:
        importlib.import_module(m); print("   ✓", m)
    except Exception as e:
        print("   ✗", m, e)
PY

echo
bash "$HERE/fetch_models.sh"

cat <<EOF

✓ نصب کامل شد.

میان‌بر سریع:
  export ASR_VENV="$VENV"
  $VENV/bin/python "$HERE/transcribe.py" INPUT.mp4 --engine auto --language fa
  $VENV/bin/python "$HERE/make_joze.py" --transcript out/INPUT.json --title "جزوه"

EOF
