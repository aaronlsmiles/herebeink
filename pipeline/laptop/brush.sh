#!/usr/bin/env bash
# Mac fallback: train the same set with Brush (Apple-silicon build) when the laptop cannot.
#   laptop/brush.sh                       work/train -> work/splat/brush/
#   laptop/brush.sh work/train_dry 500    a quick check of the flags and the loader
# Brush is not installed by this pipeline; it is a dependency to approve first (release v0.3.0).
set -euo pipefail
cd "$(dirname "$0")/.."
DATA=${1:-work/train}
ITERS=${2:-30000}
OUT=work/splat/brush
mkdir -p "$OUT"

if ! command -v brush >/dev/null 2>&1; then
  echo "Brush is not installed. It is a new dependency: ask before installing (Apple-silicon release v0.3.0)." >&2
  exit 2
fi
brush --help > "$OUT/brush-help.txt" 2>&1 || true
missing=""
for flag in --total-train-iters --max-splats --max-resolution --export-path; do
  grep -q -- "$flag" "$OUT/brush-help.txt" || missing="$missing $flag"
done
if [ -n "$missing" ]; then
  echo "This Brush build does not list:$missing. Read $OUT/brush-help.txt and change the flags below." >&2
  exit 3
fi
start=$(date +%s)
brush "$DATA" --total-train-iters "$ITERS" --max-splats 1500000 --max-resolution 1440 --export-path "$OUT" 2>&1 | tee "$OUT/brush-output.txt"
echo "Brush took $(( ($(date +%s) - start) / 60 )) minutes; output in $OUT" | tee -a "$OUT/brush-output.txt"
