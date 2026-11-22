"""Small wrappers over ffprobe and Pillow, so the scripts read media facts one way."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

PASSES = ("raised", "head", "hip", "key")
ROOM_PASSES = ("raised", "head", "hip")
# Same stand position: manual exposure (cut into views for COLMAP), auto exposure (likely the one
# sent to Marble), HDR. Any of them may be uploaded, so every one gets a privacy sheet.
PANO_STEMS = ("pano", "pano-auto", "pano-hdr")


class MediaError(Exception):
    """A masked copy and its source disagree; the message says what to do."""


def _rate(text: str) -> float:
    num, _, den = text.partition("/")
    return float(num) / float(den) if den and float(den) else 0.0


def probe_video(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames:format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout
    data = json.loads(out)
    if not data.get("streams"):
        raise ValueError(f"{path.name} has no video stream")
    s = data["streams"][0]
    fps = _rate(s.get("avg_frame_rate", "0/0")) or _rate(s.get("r_frame_rate", "0/0"))
    duration = float(data.get("format", {}).get("duration", 0.0))
    frames = int(s["nb_frames"]) if str(s.get("nb_frames", "")).isdigit() else round(duration * fps)
    return {"codec": s.get("codec_name", "?"), "width": int(s["width"]), "height": int(s["height"]),
            "fps": round(fps, 3), "duration_s": round(duration, 3), "frames": frames,
            "avg_fps": round(_rate(s.get("avg_frame_rate", "0/0")), 3),
            "r_fps": round(_rate(s.get("r_frame_rate", "0/0")), 3)}


def image_size(path: Path) -> tuple[int, int]:
    """Stored pixel size; EXIF orientation is ignored on purpose, as COLMAP ignores it too."""
    with Image.open(path) as im:
        return im.size


def focal_35mm(path: Path) -> int | None:
    with Image.open(path) as im:
        value = im.getexif().get_ifd(0x8769).get(0xA405)
    return int(value) if value else None


def original_of(path: Path) -> tuple[Path, bool]:
    """(the unmasked file, whether `path` is itself a masked copy): pass-head.masked.mp4 -> pass-head.mp4."""
    if path.stem.endswith(".masked"):
        return path.with_name(path.stem[: -len(".masked")] + path.suffix), True
    return path, False


def masked_twin(original: Path) -> Path:
    return original.with_name(f"{original.stem}.masked{original.suffix}")


def resolve_source(path: Path) -> Path:
    """The one rule for which file to read: the privacy-masked copy when one exists, else the export.

    A masked copy is a black-boxed rendering of its source, so it is read instead of the source, never
    beside it. A masked copy older than its source was made from an earlier export and hides the wrong
    things in the new one: refuse it rather than carry it forward.
    """
    original, is_masked = original_of(Path(path))
    masked = masked_twin(original)
    if not masked.exists():
        return original
    if original.exists() and masked.stat().st_mtime_ns < original.stat().st_mtime_ns:
        raise MediaError(f"{masked.name} is older than {original.name}, which was exported again: "
                         f"delete {masked.name} and mask the new export again")
    return masked


def choose_source(path: Path) -> Path:
    """For a file an operator names: refuse the unmasked source when its masked copy exists."""
    path = Path(path)
    resolved = resolve_source(path)
    if resolved != path:
        raise MediaError(f"{resolved.name} exists beside {path.name}: pass the masked copy, "
                         "the original is what the privacy pass hid things in")
    return path


def stitched_video(stitched: Path, name: str) -> Path:
    return resolve_source(stitched / f"pass-{name}.mp4")


def stitched_pano(stitched: Path, stem: str = "pano") -> Path:
    return resolve_source(stitched / f"{stem}.jpg")
