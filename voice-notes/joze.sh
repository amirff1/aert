#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  یک‌مرحله‌ای: فایل صوتی/ویدیویی یا پاورپوینت → جزوه
#  استفاده:  bash joze.sh INPUT.pptx [--language fa] [--title "عنوان"] [--out out]
# ---------------------------------------------------------------------------
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${ASR_VENV:-$HOME/asr-venv}/bin/python"

if [ $# -lt 1 ]; then
  echo "استفاده: bash joze.sh INPUT.(pptx|mp4|mp3|…) [--language fa] [--title «عنوان»] [--out out]"
  exit 1
fi

IN="$1"; shift || true
LANG_ARG=""; TITLE=""; OUT="out"
while [ $# -gt 0 ]; do
  case "$1" in
    --language|-l) LANG_ARG="$2"; shift 2;;
    --title|-t)    TITLE="$2";    shift 2;;
    --out|-o)      OUT="$2";      shift 2;;
    *) shift;;
  esac
done
STEM="$(basename "${IN%.*}")"
[ -z "$TITLE" ] && TITLE="جزوهٔ $STEM"

echo "=== ۱) پیاده‌سازی صدا ==="
if [ -n "$LANG_ARG" ]; then
  "$PY" "$HERE/transcribe.py" "$IN" --language "$LANG_ARG" --out "$OUT"
else
  "$PY" "$HERE/transcribe.py" "$IN" --out "$OUT"
fi

echo
echo "=== ۲) ساخت جزوه ==="
SLIDES_ARG=()
[ -f "$OUT/slides/slides.json" ] && SLIDES_ARG=(--slides "$OUT/slides/slides.json")
"$PY" "$HERE/make_joze.py" "${SLIDES_ARG[@]}" --transcript-dir "$OUT" \
      --title "$TITLE" --out "$OUT"

echo
echo "✓ تمام. جزوه: $OUT/joze.html  و  $OUT/joze.md"
