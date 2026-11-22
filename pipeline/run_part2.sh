#!/usr/bin/env bash
# Part 2 on the real data, after splat_raw.ply is back from the laptop (work/splat/) and a Marble world
# has been generated and exported (work/marble/<id>.json and marble_<id>.ply).
#
#   ./run_part2.sh WORLD_ID door        # writes work/door/pick.html; click, paste into NOTES.md, then:
#   ./run_part2.sh WORLD_ID scale       # scale, floor, world frame; the proposed cleaning box and box.png
#   ./run_part2.sh WORLD_ID clean       # crop with the box in NOTES.md -> measured.ply
#   ./run_part2.sh WORLD_ID align       # Gate A: the residual, the table and work/align/<id>/contact.png
#   ./run_part2.sh WORLD_ID finish      # provenance, coastline, export -> work/export/v1/
#   ./run_part2.sh WORLD_ID doorway     # the kill rule's second stage: align a doorway world instead
#
# Each stage stops where a person looks or types something; nothing is uploaded here. Extra arguments go
# to the stage's main script: scale --accept "reason", align --start ... or --accept-by-eye "reason",
# finish --allow-failed-gate "reason".
# WORK and NOTES default to work/ and ../capture/NOTES.md; set them to rehearse on a synthetic day.
set -euo pipefail
cd "$(dirname "$0")"
WORLD=${1:?world id}
STAGE=${2:?stage: door, scale, clean, align, finish or doorway}
shift 2
PY="uv run --frozen python"
W=(--work "${WORK:-work}")
N=(--notes "${NOTES:-../capture/NOTES.md}")
NO_CLICKS=3

case "$STAGE" in
  door)
    $PY door_points.py "${W[@]}" "${N[@]}" page
    echo "Click both corners in two or more views, paste the lines under 'Later' in NOTES.md, then: $0 $WORLD scale" ;;
  scale)
    rc=0
    $PY door_points.py "${W[@]}" "${N[@]}" solve "$@" || rc=$?
    if [ "$rc" -eq "$NO_CLICKS" ]; then
      echo "no door clicks: trying the SuperSplat picks"
    elif [ "$rc" -ne 0 ]; then
      echo "Door clicks refused (above). Re-click, or after looking: $0 $WORLD scale --accept \"reason\"" >&2
      exit "$rc"
    fi
    if ! $PY scale.py "${W[@]}" "${N[@]}" "$@"; then
      echo "Scale refused (above). Fix it, or after looking: $0 $WORLD scale --accept \"reason\"" >&2
      exit 1
    fi
    $PY clean.py "${W[@]}" "${N[@]}" propose
    echo "STOP: look at ${WORK:-work}/clean/box.png (every wall inside the red box), then paste the box line into"
    echo "NOTES.md (widen it if a wall is outside), then: $0 $WORLD clean" ;;
  clean)
    $PY clean.py "${W[@]}" "${N[@]}" apply
    echo "Optional: delete floaters in SuperSplat from measured.ply, export uncompressed PLY, then"
    echo "  $PY clean.py ${W[*]} ${N[*]} adopt EXPORT.ply"
    echo "Then: $0 $WORLD align" ;;
  align|doorway)
    mode=pano
    [ "$STAGE" = doorway ] && mode=doorway
    if ! $PY align.py "${W[@]}" "${N[@]}" --world "$WORLD" --mode "$mode" "$@"; then
      echo "Gate A FAILED (reasons above). Look at the contact sheet and the table in align.json. If a person can see" >&2
      echo "the pose is right: $0 $WORLD $STAGE --accept-by-eye \"what you saw\". Otherwise the kill rule's next stage." >&2
      exit 1
    fi
    echo "Gate A passed. Look at the contact sheet anyway (top views: from above, door arrow), then: $0 $WORLD finish" ;;
  finish)
    $PY provenance.py "${W[@]}" --world "$WORLD"
    $PY coastline.py "${W[@]}" --world "$WORLD"
    $PY export.py "${W[@]}" --world "$WORLD" "$@"
    echo "Look at the plan view (coastline.png). Upload waits for the go: upload_media.py" ;;
  *) echo "unknown stage $STAGE" >&2; exit 2 ;;
esac
