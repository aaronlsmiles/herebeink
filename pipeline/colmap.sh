#!/usr/bin/env bash
# COLMAP on the Mac (CPU build, 4.2.1): features, the eight-view rig, matching, mapping, the report.
#
#   ./colmap.sh                                   full run on work/images (about 1 to 2.5 hours for ~900 images)
#   FROM=mapper ./colmap.sh                        keep the database and matches, map again
#   PHONE=0 FROM=mapper ./colmap.sh                map without the phone stills (fallback 3)
#   EXTRA_PAIRS=work/pairs-head.txt FROM=match_extra ./colmap.sh    add pairs (fallback 2), then map
#   WORK=/some/dir ./colmap.sh                     another work folder (the smoke test uses this)
#   FROM=report ./colmap.sh                        just print the report for the model already there
#   FRESH=1 ./colmap.sh                            start over even though a finished model exists
#
# A plain run starts from scratch and deletes the folder, so it refuses while a finished model is in it.
# The mapper also writes a snapshot of the model every SNAPSHOT_FRAMES registered frames into
# $WORK/colmap/snapshots, so a mapper that dies late leaves something to look at.
#
# Every COLMAP call is logged in $WORK/colmap/colmap.log; the terminal shows one line a step.
# Written for macOS's bash 3.2: an empty array is expanded as ${a[@]+"${a[@]}"} under set -u.
set -Eeuo pipefail
# A sleeping Mac stops an hour-long mapper; caffeinate holds it awake for the whole run.
if [ -z "${COLMAP_SH_AWAKE:-}" ] && command -v caffeinate >/dev/null 2>&1; then
  exec env COLMAP_SH_AWAKE=1 caffeinate -i bash "$0" "$@"
fi
cd "$(dirname "$0")"

WORK=${WORK:-work}
IMAGES=$WORK/images
OUT=$WORK/colmap
DB=$OUT/database.db
FROM=${FROM:-extract}
PHONE=${PHONE:-1}
MAX_FEATURES=${MAX_FEATURES:-8192}
SEQ_OVERLAP=${SEQ_OVERLAP:-5}
SNAPSHOT_FRAMES=${SNAPSHOT_FRAMES:-25}
EXTRA_PAIRS=${EXTRA_PAIRS:-}
# COLMAP fetches this tree from its GitHub release on first use and caches it; passing the cached
# file means a run never needs the network.
VOCAB=${VOCAB:-$(ls "$HOME"/.cache/colmap/*vocab_tree_faiss_flickr100K_words256K.bin 2>/dev/null | head -n 1 || true)}
PY="uv run --frozen python"
CPU=(--FeatureExtraction.use_gpu 0)
MATCH=(--FeatureMatching.use_gpu 0 --FeatureMatching.rig_verification 1)
QUIET=(--log_target stderr)

stage_num() { case "$1" in extract) echo 1;; match) echo 2;; match_extra) echo 3;; mapper) echo 4;; report) echo 5;;
  *) echo "unknown FROM=$1 (extract, match, match_extra, mapper, report)" >&2; exit 2;; esac; }
START=$(stage_num "$FROM")
at() { [ "$START" -le "$(stage_num "$1")" ]; }

if at extract; then
  if [ -n "$(ls -A "$OUT/sparse" 2>/dev/null)" ] && [ "${FRESH:-0}" != 1 ]; then
    {
      echo "colmap.sh: $OUT/sparse holds a finished model, and a plain run starts over and deletes it."
      echo "  just show me the report:  FROM=report ./colmap.sh"
      echo "  map again, keep matches:  FROM=mapper ./colmap.sh"
      echo "  really start over:        FRESH=1 ./colmap.sh"
    } >&2
    exit 2
  fi
  rm -rf "$OUT"
fi
mkdir -p "$OUT"
LOG=$OUT/colmap.log
log() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }
run() { log "colmap $1"; colmap "$@" "${QUIET[@]}" >>"$LOG" 2>&1; }
trap 'log "FAILED: last lines of $LOG follow"; tail -n 25 "$LOG"' ERR

# The cube cameras are exact by construction: the 90 degree assumption lives in views.py and
# reaches COLMAP through frames.json, never typed again here.
read -r VIEW_SIZE CAMERA < <($PY -c 'import json,sys; d = json.load(open(sys.argv[1])); s = d["view_size"]; f = d["focal_px"]; print(s, f"{f},{f},{s / 2},{s / 2}")' "$WORK/frames.json")
(cd "$IMAGES" && find rig -name '*.jpg' | LC_ALL=C sort) > "$OUT/rig_images.txt"
if [ "$PHONE" = 1 ] && [ -d "$IMAGES/phone" ]; then
  (cd "$IMAGES" && find phone -name '*.jpg' | LC_ALL=C sort) > "$OUT/phone_images.txt"
else
  : > "$OUT/phone_images.txt"
fi
NO_PHONE=(); [ "$PHONE" = 1 ] || NO_PHONE=(--no-phone)
log "start at '$FROM': $(wc -l < "$OUT/rig_images.txt" | tr -d ' ') cube views, $(wc -l < "$OUT/phone_images.txt" | tr -d ' ') phone stills, view ${VIEW_SIZE}px"

if at extract; then
  run feature_extractor --database_path "$DB" --image_path "$IMAGES" --image_list_path "$OUT/rig_images.txt" \
    --ImageReader.camera_model PINHOLE --ImageReader.camera_params "$CAMERA" \
    --ImageReader.single_camera_per_folder 1 --SiftExtraction.max_num_features "$MAX_FEATURES" "${CPU[@]}"
  if [ -s "$OUT/phone_images.txt" ]; then
    run feature_extractor --database_path "$DB" --image_path "$IMAGES" --image_list_path "$OUT/phone_images.txt" \
      --ImageReader.camera_model OPENCV --ImageReader.single_camera_per_folder 1 \
      --FeatureExtraction.max_image_size 3200 --SiftExtraction.max_num_features "$MAX_FEATURES" "${CPU[@]}"
  fi
  run rig_configurator --database_path "$DB" --rig_config_path "$WORK/rig_config.json"
  $PY colmap_report.py --work "$WORK" ${NO_PHONE[@]+"${NO_PHONE[@]}"} db-check | tee -a "$LOG"
fi

if at match; then
  if [ -n "$VOCAB" ] && [ -f "$VOCAB" ]; then
    log "vocab tree: $(basename "$VOCAB") (sequential with loop detection, retrieval for the pano and phone)"
    run sequential_matcher --database_path "$DB" "${MATCH[@]}" \
      --SequentialMatching.overlap "$SEQ_OVERLAP" --SequentialMatching.quadratic_overlap 0 \
      --SequentialMatching.loop_detection 1 --SequentialMatching.vocab_tree_path "$VOCAB"
    { grep '/5pano_' "$OUT/rig_images.txt" || true; cat "$OUT/phone_images.txt"; } > "$OUT/query_images.txt"
    if [ -s "$OUT/query_images.txt" ]; then
      run vocab_tree_matcher --database_path "$DB" "${MATCH[@]}" --VocabTreeMatching.vocab_tree_path "$VOCAB" \
        --VocabTreeMatching.match_list_path "$OUT/query_images.txt" --VocabTreeMatching.num_images 50
    fi
  else
    log "no cached vocab tree: sequential matching plus the anchor pairs that tie the passes together"
    run sequential_matcher --database_path "$DB" "${MATCH[@]}" \
      --SequentialMatching.overlap "$SEQ_OVERLAP" --SequentialMatching.quadratic_overlap 0
    $PY make_pairs.py --work "$WORK" anchors ${NO_PHONE[@]+"${NO_PHONE[@]}"} > "$OUT/pairs-anchors.txt"
    run matches_importer --database_path "$DB" --match_list_path "$OUT/pairs-anchors.txt" --match_type pairs "${MATCH[@]}"
  fi
fi

if at match_extra && [ -n "$EXTRA_PAIRS" ]; then
  run matches_importer --database_path "$DB" --match_list_path "$EXTRA_PAIRS" --match_type pairs "${MATCH[@]}"
fi

if at mapper; then
  rm -rf "$OUT/sparse" "$OUT/sparse_txt" "$OUT/snapshots"
  mkdir -p "$OUT/sparse" "$OUT/sparse_txt" "$OUT/snapshots"
  # the cube cameras are exact by construction; only the phone cameras' intrinsics are refined
  sqlite3 "$DB" "select distinct camera_id from images where name like 'rig/%' order by camera_id;" > "$OUT/constant_cameras.txt"
  ONLY_RIG=(); [ "$PHONE" = 1 ] || ONLY_RIG=(--Mapper.image_list_path "$OUT/rig_images.txt")
  run mapper --database_path "$DB" --image_path "$IMAGES" --output_path "$OUT/sparse" \
    --Mapper.ba_refine_focal_length 1 --Mapper.ba_refine_principal_point 0 --Mapper.ba_refine_extra_params 1 \
    --Mapper.ba_refine_sensor_from_rig 0 --Mapper.constant_camera_list_path "$OUT/constant_cameras.txt" \
    --Mapper.snapshot_path "$OUT/snapshots" --Mapper.snapshot_frames_freq "$SNAPSHOT_FRAMES" ${ONLY_RIG[@]+"${ONLY_RIG[@]}"}
  for m in "$OUT"/sparse/*/; do
    [ -d "$m" ] || continue
    k=$(basename "$m")
    mkdir -p "$OUT/sparse_txt/$k"
    run model_converter --input_path "$m" --output_path "$OUT/sparse_txt/$k" --output_type TXT
  done
fi

trap - ERR
log "report"
$PY colmap_report.py --work "$WORK" ${NO_PHONE[@]+"${NO_PHONE[@]}"} report | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
