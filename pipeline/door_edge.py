"""The door plane, and the doorway past it, as a hard edge: the one definition every stage reads.

The measured world ends at the door frame (hub call 62): what the trained splat holds past it is fog seen
through the doorway, not a measurement. So inside the opening and past the plane (the "sealed" prism),
measured splats are trimmed and every Marble splat is imagined, whatever its distance to the measured
world. The jambs, the head and the wall either side are outside the prism and keep the distance rule, so
the frame itself is never sliced.

The plane is scale.json's door centre with its outward normal (out of the room). The opening is the
tape width between the jambs and the head corners' height, each pulled in by a margin so splats lying on
a jamb's or the head's face are not cut.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# A jamb's splats straddle its face; 2 cm in keeps them (Part 1's splats are a few cm across at the door).
JAMB_MARGIN_M = 0.02
HEAD_MARGIN_M = 0.03


def door_plane(scale: dict) -> tuple[np.ndarray, np.ndarray]:
    d = scale["door"]
    c = np.asarray(d["centre"], float)
    n = np.asarray(d["outward"], float)
    return c, n / np.linalg.norm(n)


@dataclass(frozen=True)
class Opening:
    centre: np.ndarray
    normal: np.ndarray
    lateral: np.ndarray
    half_width: float
    top: float


def opening(scale: dict) -> Opening:
    c, n = door_plane(scale)
    d = scale["door"]
    lateral = np.array([-n[2], 0.0, n[0]])
    lateral /= np.linalg.norm(lateral)
    top = float(np.mean([p[1] for p in d["top"]])) - HEAD_MARGIN_M if d.get("top") else np.inf
    return Opening(c, n, lateral, float(d["width_tape_m"]) / 2 - JAMB_MARGIN_M, top)


def past_plane(pts: np.ndarray, scale: dict) -> np.ndarray:
    c, n = door_plane(scale)
    return (np.atleast_2d(pts) - c) @ n > 0


def sealed(pts: np.ndarray, scale: dict) -> np.ndarray:
    """Points past the door plane and inside the opening's prism (between the jambs, below the head)."""
    o = opening(scale)
    rel = np.atleast_2d(np.asarray(pts, float)) - o.centre
    return (rel @ o.normal > 0) & (np.abs(rel @ o.lateral) < o.half_width) & (rel[:, 1] + o.centre[1] < o.top)


def through_opening(origin: np.ndarray, dirs_world: np.ndarray, scale: dict) -> np.ndarray:
    """Rays from origin (on the room side) that leave the room through the opening."""
    o = opening(scale)
    d = np.atleast_2d(np.asarray(dirs_world, float))
    dn = d @ o.normal
    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((o.centre - origin) @ o.normal) / dn
    p = origin + d * np.where(dn > 1e-9, t, 0.0)[:, None]
    rel = p - o.centre
    return (dn > 1e-9) & (t > 0) & (np.abs(rel @ o.lateral) < o.half_width) & (p[:, 1] < o.top) & (p[:, 1] > -0.05)
