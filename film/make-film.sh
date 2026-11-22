#!/usr/bin/env bash
# The film in one command: dump every shot in both aspects, take the page shots, then cut (film/README.md).
# Usage: film/make-film.sh [export folder, relative to the repo; default pipeline/work/export/v2]
# Re-cut only (frames already dumped, e.g. after adding film/takes/headset.mp4): cd web && node tools/film-cut.mjs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXPORT="${1:-pipeline/work/export/v2}"
cd "$ROOT/web"
for A in 16x9 9x16; do
  case "$A" in
    16x9) W=1920; H=1080 ;;
    9x16) W=1080; H=1350 ;;
  esac
  for S in hook walk switch outro; do
    node tools/film-dump.mjs --export "$EXPORT" --shot "$S" --set "$A-$S" --w "$W" --h "$H"
  done
  node tools/film-dump.mjs --export "$EXPORT" --shot switch --ink off --set "$A-switch-filter" --w "$W" --h "$H"
  node tools/film-shots.mjs --export "$EXPORT" --aspect "$A"
done
node tools/film-cut.mjs
