"""SPZ files: written by Spark's own encoder (spz/transcode.mjs, Node), read back here for their header.

Spark 2.4.0 is already pinned in web/package.json for the viewer; using its encoder means the files are
written by the same code that will decode them, at the same version.
"""
from __future__ import annotations

import gzip
import json
import struct
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "spz" / "transcode.mjs"
MAGIC = 0x5053474E  # "NGSP"


def transcode(jobs: list[tuple[Path, Path]], max_sh: int = 3) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([{"in": str(a), "out": str(b), "maxSh": max_sh} for a, b in jobs], f)
    proc = subprocess.run(["node", str(SCRIPT), f.name], capture_output=True, text=True)
    Path(f.name).unlink()
    if proc.returncode != 0:
        raise RuntimeError(f"spz/transcode.mjs failed: {proc.stderr.strip() or proc.stdout.strip()}")


def header(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        magic, version, count, sh, bits, flags, _ = struct.unpack("<IIIBBBB", f.read(16))
    if magic != MAGIC:
        raise ValueError(f"{path.name} is not an SPZ file")
    return {"version": version, "splats": count, "shDegree": sh, "fractionalBits": bits, "flags": flags}
