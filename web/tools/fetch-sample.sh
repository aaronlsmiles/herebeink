#!/usr/bin/env bash
set -euo pipefail
dest="$(cd "$(dirname "$0")/.." && pwd)/public/sample"
mkdir -p "$dest"
curl -fsSL -o "$dest/butterfly.spz" "https://sparkjs.dev/assets/splats/butterfly.spz"
echo "saved $dest/butterfly.spz"
