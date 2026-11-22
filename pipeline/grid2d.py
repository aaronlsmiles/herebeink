"""A floor grid in the world frame's x-z plane: occupancy, marching squares, Chaikin smoothing.

Rows run along z and columns along x; cell (i, j) is centred at (x0 + (j + 0.5) * cell, z0 + (i + 0.5) * cell).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class Grid:
    x0: float
    z0: float
    cell: float
    nx: int
    nz: int

    @staticmethod
    def around(xz: np.ndarray, cell: float, margin_cells: int = 3) -> "Grid":
        lo = np.floor(xz.min(axis=0) / cell) * cell - margin_cells * cell
        hi = np.ceil(xz.max(axis=0) / cell) * cell + margin_cells * cell
        nx, nz = (np.round((hi - lo) / cell).astype(int))
        return Grid(float(lo[0]), float(lo[1]), cell, int(nx), int(nz))

    def occupancy(self, xz: np.ndarray) -> np.ndarray:
        j = np.floor((xz[:, 0] - self.x0) / self.cell).astype(int)
        i = np.floor((xz[:, 1] - self.z0) / self.cell).astype(int)
        ok = (i >= 0) & (i < self.nz) & (j >= 0) & (j < self.nx)
        mask = np.zeros((self.nz, self.nx), bool)
        mask[i[ok], j[ok]] = True
        return mask

    def disks(self, xz: np.ndarray, radius: float) -> np.ndarray:
        """Cells whose centre lies within radius of any point."""
        jj, ii = np.meshgrid(np.arange(self.nx), np.arange(self.nz))
        centres = np.stack([self.x0 + (jj + 0.5) * self.cell, self.z0 + (ii + 0.5) * self.cell], -1).reshape(-1, 2)
        from scipy.spatial import cKDTree
        d, _ = cKDTree(xz).query(centres, workers=-1)
        return (d <= radius).reshape(self.nz, self.nx)

    def to_world(self, rc: np.ndarray) -> np.ndarray:
        """(row, col) in cell-centre index units -> (x, z)."""
        return np.stack([self.x0 + (rc[:, 1] + 0.5) * self.cell, self.z0 + (rc[:, 0] + 0.5) * self.cell], -1)

    def cell_of(self, xz: np.ndarray) -> np.ndarray:
        return np.stack([np.floor((xz[:, 1] - self.z0) / self.cell), np.floor((xz[:, 0] - self.x0) / self.cell)], -1).astype(int)


def close(mask: np.ndarray, size: int = 3) -> np.ndarray:
    return ndimage.binary_closing(mask, structure=np.ones((size, size)), border_value=0)


# Edges of a 2 x 2 block of samples, as (row, col) offsets of their midpoints.
_EDGE = {"top": (0.0, 0.5), "right": (0.5, 1.0), "bottom": (1.0, 0.5), "left": (0.5, 0.0)}
# Corner bits: top-left 8, top-right 4, bottom-right 2, bottom-left 1. Saddles keep diagonal corners apart.
_CASES = {1: [("left", "bottom")], 2: [("bottom", "right")], 3: [("left", "right")], 4: [("top", "right")],
          5: [("left", "bottom"), ("top", "right")], 6: [("top", "bottom")], 7: [("left", "top")],
          8: [("left", "top")], 9: [("top", "bottom")], 10: [("left", "top"), ("bottom", "right")],
          11: [("top", "right")], 12: [("left", "right")], 13: [("bottom", "right")], 14: [("left", "bottom")]}


def contour_segments(mask: np.ndarray) -> np.ndarray:
    """Marching squares on cell centres: segments (k, 2, 2) of (row, col) points on the 0.5 level."""
    m = np.pad(mask.astype(np.uint8), 1)
    code = (m[:-1, :-1] << 3) | (m[:-1, 1:] << 2) | (m[1:, 1:] << 1) | m[1:, :-1]
    segs = []
    for case, pairs in _CASES.items():
        rows, cols = np.nonzero(code == case)
        for a, b in pairs:
            pa = np.stack([rows + _EDGE[a][0], cols + _EDGE[a][1]], -1)
            pb = np.stack([rows + _EDGE[b][0], cols + _EDGE[b][1]], -1)
            segs.append(np.stack([pa, pb], 1))
    if not segs:
        return np.zeros((0, 2, 2))
    return np.concatenate(segs) - 1.0  # undo the padding


def link(segments: np.ndarray) -> list[tuple[np.ndarray, bool]]:
    """Join segments sharing end points into polylines; returns (points, closed) pairs."""
    key = lambda p: (round(float(p[0]) * 2), round(float(p[1]) * 2))  # noqa: E731
    ends: dict[tuple, list[int]] = {}
    for k, (a, b) in enumerate(segments):
        ends.setdefault(key(a), []).append(k)
        ends.setdefault(key(b), []).append(k)
    used = np.zeros(len(segments), bool)
    out = []
    for start in range(len(segments)):
        if used[start]:
            continue
        used[start] = True
        chain = [segments[start][0], segments[start][1]]
        for direction in (1, 0):
            while True:
                tip = chain[-1] if direction else chain[0]
                nxt = next((k for k in ends.get(key(tip), []) if not used[k]), None)
                if nxt is None:
                    break
                used[nxt] = True
                a, b = segments[nxt]
                p = b if key(a) == key(tip) else a
                if direction:
                    chain.append(p)
                else:
                    chain.insert(0, p)
        pts = np.array(chain)
        closed = len(pts) > 3 and key(pts[0]) == key(pts[-1])
        out.append((pts[:-1] if closed else pts, closed))
    return out


def chaikin(points: np.ndarray, closed: bool, rounds: int = 2) -> np.ndarray:
    p = np.asarray(points, float)
    for _ in range(rounds):
        if len(p) < 3:
            return p
        a, b = (p, np.roll(p, -1, axis=0)) if closed else (p[:-1], p[1:])
        q, r = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
        new = np.empty((2 * len(a), p.shape[1]))
        new[0::2], new[1::2] = q, r
        p = new if closed else np.vstack([p[:1], new, p[-1:]])
    return p


def polygons(grid: Grid, mask: np.ndarray, min_area_m2: float = 0.25) -> list[list[list[float]]]:
    """Closed outlines of a mask in metres, largest first, small islands dropped."""
    out = []
    for pts, closed in link(contour_segments(mask)):
        if not closed:
            continue
        xz = grid.to_world(pts)
        area = 0.5 * abs(np.dot(xz[:, 0], np.roll(xz[:, 1], -1)) - np.dot(xz[:, 1], np.roll(xz[:, 0], -1)))
        if area >= min_area_m2:
            out.append((area, xz))
    out.sort(key=lambda t: -t[0])
    return [[[round(float(x), 4), round(float(z), 4)] for x, z in xz] for _, xz in out]
