#!/usr/bin/env bash
# Builds the viewer and stages exactly what ships into deploy/production/ (gitignored): the static
# build and vercel.json. The splat files and scene.json are not part of it: they live on the media
# host, and VITE_SCENE_URL (required) is baked into the build as the page's default scene.
# The identifier scan is part of the stage: IDENTIFIER_SCAN (the path of a scanner script, in the
# environment or the gitignored .env.local) is required, and a missing scanner refuses the stage.
# Usage: VITE_SCENE_URL=https://<media-host>/<prefix>/scene.json tools/deploy/stage.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
out="$here/deploy/production"
: "${VITE_SCENE_URL:?set VITE_SCENE_URL to the scene.json URL on the media host}"
export VITE_SCENE_URL

# The environment wins; .env.local is read in a subshell so it cannot override anything else.
from_local() { [ -f "$here/.env.local" ] || return 0; ( set -a; . "$here/.env.local"; printf '%s' "${!1:-}" ); }
scan="${IDENTIFIER_SCAN:-$(from_local IDENTIFIER_SCAN)}"
[ -n "$scan" ] || { echo "refusing: set IDENTIFIER_SCAN in .env.local to the identifier scanner script (see REDEPLOY.md)" >&2; exit 2; }
[ -x "$scan" ] || { echo "refusing: the identifier scanner $scan is missing or not executable" >&2; exit 2; }

(cd "$here/web" && npm run build --silent)

# Keep the Vercel link between deploys; replace everything else.
mkdir -p "$out"
find "$out" -mindepth 1 -maxdepth 1 ! -name .vercel -exec rm -rf {} +
# The fixture and the butterfly sample are test data, the spike and smoke pages are internal, and
# source maps would publish the source layout.
rsync -a \
  --exclude '/fixture/' --exclude '/sample/' --exclude '/spike.html' --exclude '/smoke.html' \
  --exclude '*.map' \
  "$here/web/dist/" "$out/"
cp "$here/tools/deploy/vercel.json" "$out/vercel.json"

# Media never ships through the page host: a splat file here means the exclusions above missed something.
if find "$out" \( -name '*.spz' -o -name '*.ply' -o -name '*.rad' -o -name '*.map' -o -name 'spike*' -o -name 'smoke*' \) -not -path "$out/.vercel/*" | grep -q .; then
  echo "refusing: the staged folder holds media, source maps or internal pages:" >&2
  find "$out" \( -name '*.spz' -o -name '*.ply' -o -name '*.rad' -o -name '*.map' -o -name 'spike*' -o -name 'smoke*' \) -not -path "$out/.vercel/*" >&2
  exit 1
fi
[ -f "$out/index.html" ] || { echo "refusing: no index.html in the staged folder" >&2; exit 1; }

# The identifier scan runs on exactly what ships (not .vercel/, the local project link, never uploaded as content).
scan_targets=()
while IFS= read -r f; do scan_targets+=("$f"); done < <(find "$out" -mindepth 1 -maxdepth 1 ! -name .vercel)
"$scan" "${scan_targets[@]}"

bytes="$(find "$out" -type f -not -path "$out/.vercel/*" -exec stat -f %z {} + | awk '{s+=$1} END {print s+0}')"
files="$(find "$out" -type f -not -path "$out/.vercel/*" | wc -l | tr -d ' ')"
gz="$(find "$out" -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' \) -not -path "$out/.vercel/*" -exec sh -c 'gzip -9 -c "$1" | wc -c' _ {} \; | awk '{s+=$1} END {print s+0}')"
echo "staged: $out"
echo "size: $bytes bytes in $files files (js, css and html gzip to $gz bytes)"
