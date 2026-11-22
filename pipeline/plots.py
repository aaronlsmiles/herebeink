"""Top and side views drawn with Pillow, shared by the contact sheet, the plan view and the cleaning box.

Seen from above (looking down -y) with +x to the right, +z points down the page: the world frame is
right-handed with +y up. Drawing z up the page with x to the right is the view from below, a mirror image.
"""
from __future__ import annotations

import numpy as np
from PIL import ImageDraw

SLICE_M = (0.3, 1.5)  # furniture and walls stand out; floor and ceiling would cover them


class Panel:
    """World coordinates (a, b) into a pixel box, with equal metres per pixel on both axes.

    top=True: a = x to the right, b = z down the page (from above). top=False: a = x right, b = y up.
    """

    def __init__(self, box, lo, hi, top: bool):
        self.box, self.top = box, top
        x0, y0, x1, y1 = box
        lo, hi = np.asarray(lo, float), np.asarray(hi, float)
        span = np.maximum(hi - lo, 1e-9)
        self.k = min((x1 - x0) / span[0], (y1 - y0) / span[1])
        self.lo, self.hi = lo, hi
        # centre the drawing in the box
        self.off = np.array([x0 + ((x1 - x0) - span[0] * self.k) / 2, y0 + ((y1 - y0) - span[1] * self.k) / 2])

    def px(self, ab: np.ndarray) -> np.ndarray:
        ab = np.atleast_2d(np.asarray(ab, float))
        u = self.off[0] + (ab[:, 0] - self.lo[0]) * self.k
        if self.top:
            v = self.off[1] + (ab[:, 1] - self.lo[1]) * self.k
        else:
            v = self.off[1] + (self.hi[1] - ab[:, 1]) * self.k
        return np.stack([u, v], -1)

    def points(self, draw: ImageDraw.ImageDraw, ab: np.ndarray, colour) -> None:
        if not len(ab):
            return
        uv = self.px(ab)
        x0, y0, x1, y1 = self.box
        ok = (uv[:, 0] > x0) & (uv[:, 0] < x1) & (uv[:, 1] > y0) & (uv[:, 1] < y1)
        for u, v in uv[ok]:
            draw.point((float(u), float(v)), fill=colour)

    def axes(self, draw: ImageDraw.ImageDraw, font) -> None:
        x0, y0, x1, y1 = self.box
        ox, oy = x0 + 14, y1 - 14
        down = "+z" if self.top else "+y"
        vy = oy + 0 if self.top else oy
        draw.line([(ox, oy), (ox + 40, oy)], fill=(0, 0, 0), width=2)
        draw.text((ox + 44, oy - 9), "+x", fill=(0, 0, 0), font=font)
        if self.top:
            draw.line([(ox, oy - 52), (ox, oy - 12)], fill=(0, 0, 0), width=2)
            draw.polygon([(ox - 5, oy - 18), (ox + 5, oy - 18), (ox, oy - 10)], fill=(0, 0, 0))
            draw.text((ox + 6, oy - 52), down, fill=(0, 0, 0), font=font)
        else:
            draw.line([(ox, vy), (ox, vy - 40)], fill=(0, 0, 0), width=2)
            draw.polygon([(ox - 5, vy - 34), (ox + 5, vy - 34), (ox, vy - 42)], fill=(0, 0, 0))
            draw.text((ox + 6, vy - 52), down, fill=(0, 0, 0), font=font)
        draw.polygon([(ox + 34, oy - 5), (ox + 34, oy + 5), (ox + 42, oy)], fill=(0, 0, 0))

    def arrow(self, draw: ImageDraw.ImageDraw, frm, to, label: str, font, colour=(180, 20, 20)) -> None:
        """An arrow pointing from one place on the plan towards another, like a north arrow, with a label."""
        a, b = self.px(frm)[0], self.px(to)[0]
        d = b - a
        n = np.linalg.norm(d)
        if n < 1e-6:
            return
        d /= n
        tip = a + d * min(n, 70)
        draw.line([tuple(a), tuple(tip)], fill=colour, width=3)
        side = np.array([-d[1], d[0]])
        draw.polygon([tuple(tip + d * 6), tuple(tip - d * 8 + side * 6), tuple(tip - d * 8 - side * 6)], fill=colour)
        draw.text(tuple(tip + d * 10 + np.array([2, -8])), label, fill=colour, font=font)


def band(world: np.ndarray, lo: float = SLICE_M[0], hi: float = SLICE_M[1]) -> np.ndarray:
    return world[(world[:, 1] >= lo) & (world[:, 1] <= hi)]


def thin(pts: np.ndarray, n: int, seed: int = 0) -> np.ndarray:
    if len(pts) <= n:
        return pts
    return pts[np.random.default_rng(seed).choice(len(pts), n, replace=False)]
