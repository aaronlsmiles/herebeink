"""Gaussian-splat PLY files and similarity transforms, shared by the part 2 scripts.

Splat files are never rewritten in another frame: rows are kept or dropped with every attribute as it
was, and each file's way into the world frame is a 4 x 4 similarity (uniform scale, rotation,
translation) that the viewer sets as the mesh's matrix. Spark evaluates spherical harmonics in the
mesh's own frame, so a rotated mesh shades correctly; rotating the file instead would need the SH
coefficients rotated too, which Spark 2.4.0's transcoder does not do (tested 18 Nov 2026).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

SH_C0 = 0.28209479177387814
# Indices (within one colour channel's f_rest block, degrees 1 to 3) of the real SH basis functions that
# change sign under x -> -x: x, xy, xz, xyz, x(4z^2-x^2-y^2), x(x^2-3y^2). tests/test_splats.py checks
# them against the basis itself.
SH_ODD_IN_X = (2, 3, 6, 9, 12, 14)


class PlyFormatError(ValueError):
    """A PLY this pipeline cannot read as an uncompressed 3DGS splat file, said in words."""


def check_format(ply: PlyData, name: str) -> None:
    names = [e.name for e in ply.elements]
    if "vertex" not in names:
        raise PlyFormatError(f"{name} has no vertex element (elements: {', '.join(names) or 'none'}); "
                             "export it again as an uncompressed 3DGS PLY")
    props = ply["vertex"].data.dtype.names
    if "chunk" in names or any(p.startswith("packed_") for p in props):
        raise PlyFormatError(f"{name} is a compressed PLY (SuperSplat's 'compressed' export: packed properties "
                             "in chunks); export it again from SuperSplat as an uncompressed PLY")
    if not {"x", "y", "z"} <= set(props):
        raise PlyFormatError(f"{name} has no x, y, z on its vertices (properties: {', '.join(props)}); "
                             "it is not a splat file this pipeline can read")


def sh_degree(ply: PlyData) -> int | None:
    props = ply["vertex"].data.dtype.names
    if "f_dc_0" not in props:
        return None
    rest = sum(1 for p in props if p.startswith("f_rest_"))
    for d in range(4):
        if rest == 3 * ((d + 1) ** 2 - 1):
            return d
    raise PlyFormatError(f"{rest} f_rest coefficients is not 3 x ((d + 1)^2 - 1) for any SH degree up to 3")


def describe(ply: PlyData, name: str) -> str:
    v = ply["vertex"].data
    props = v.dtype.names
    deg = sh_degree(ply)
    lines = [f"{name}: {len(v)} splats; SH degree {deg if deg is not None else 'none (no f_dc)'}"]
    if "opacity" in props and len(v):
        op = opacity(ply)
        lines.append(f"  opacity {op.min():.3f} to {op.max():.3f} (median {np.median(op):.3f})")
    lines.append("  properties: " + " ".join(props))
    for e in ply.elements:
        if e.name != "vertex":
            lines.append(f"  element {e.name} ({len(e.data)}) is dropped from every file this pipeline writes")
    return "\n".join(lines)


def read(path: Path, quiet: bool = False) -> PlyData:
    """Read a splat PLY, refuse a compressed or unexpected one in words, and say what it holds."""
    ply = PlyData.read(str(path))
    check_format(ply, Path(path).name)
    if not quiet:
        print(describe(ply, Path(path).name))
    return ply


def count(path: Path) -> int:
    """Splat count from the header alone."""
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("ascii", "replace").strip()
            if line.startswith("element vertex"):
                return int(line.split()[2])
            if line == "end_header":
                break
    raise ValueError(f"{path.name} has no vertex element")


def centres(ply: PlyData) -> np.ndarray:
    v = ply["vertex"].data
    return np.stack([v["x"], v["y"], v["z"]], axis=1).astype(np.float64)


def opacity(ply: PlyData) -> np.ndarray:
    """Opacity in 0..1 (files store the logit)."""
    return 1.0 / (1.0 + np.exp(-ply["vertex"].data["opacity"].astype(np.float64)))


def base_colour(ply: PlyData) -> np.ndarray | None:
    """RGB in 0..1 from the degree-0 SH term, or None for a file without one."""
    v = ply["vertex"].data
    if "f_dc_0" not in v.dtype.names:
        return None
    return np.clip(0.5 + SH_C0 * np.stack([v[f"f_dc_{i}"] for i in range(3)], 1).astype(np.float64), 0, 1)


def mirror_x(rows: np.ndarray) -> np.ndarray:
    """The same splats reflected through x = 0, as rows a renderer can draw with a proper rotation.

    Centres and normals change sign in x. A Gaussian's covariance R S^2 R^T becomes Mx R S^2 R^T Mx,
    which is (Mx R Mx) S^2 (Mx R Mx)^T, and Mx R Mx is the quaternion (w, x, -y, -z). View-dependent
    colour must satisfy c'(Mx d) = c(d), so the SH coefficients odd in x change sign.
    """
    out = rows.copy()
    names = rows.dtype.names
    for p in ("x", "nx", "rot_2", "rot_3"):
        if p in names:
            out[p] = -rows[p]
    rest = sorted((p for p in names if p.startswith("f_rest_")), key=lambda p: int(p.rsplit("_", 1)[1]))
    if rest:
        k = len(rest) // 3
        for c in range(3):
            for i in SH_ODD_IN_X:
                if i < k:
                    out[f"f_rest_{c * k + i}"] = -rows[f"f_rest_{c * k + i}"]
    return out


def write_subset(ply: PlyData, keep, path: Path, rows: np.ndarray | None = None) -> int:
    """Write the kept rows with every attribute, comment and obj_info line untouched (or, given rows, those
    rows in their place, still with the source's comments)."""
    rows = (ply["vertex"].data if rows is None else rows)[keep]
    path.parent.mkdir(parents=True, exist_ok=True)
    # Comments carry any provenance or watermark data the source embedded; they must travel with the rows.
    PlyData([PlyElement.describe(rows, "vertex")], text=False, byte_order="<",
            comments=list(ply.comments), obj_info=list(ply.obj_info)).write(str(path))
    return len(rows)


def write_splats(path: Path, xyz: np.ndarray, rgb: np.ndarray, normal: np.ndarray, tangent: np.ndarray,
                 size: float, thickness: float = 0.004, alpha: float = 0.95) -> None:
    """Flat, surface-aligned splats with degree-0 colour; used for the synthetic rooms only."""
    n = len(xyz)
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
             "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    arr = np.zeros(n, dtype=[(k, "<f4") for k in names])
    arr["x"], arr["y"], arr["z"] = xyz.T
    for i in range(3):
        arr[f"f_dc_{i}"] = (np.clip(rgb[:, i], 0, 1) - 0.5) / SH_C0
    arr["opacity"] = np.log(alpha / (1 - alpha))
    arr["scale_0"] = arr["scale_1"] = np.log(size)
    arr["scale_2"] = np.log(thickness)
    q = quats_from_frames(tangent, np.cross(normal, tangent), normal)
    for i in range(4):
        arr[f"rot_{i}"] = q[:, i]
    path.parent.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(arr, "vertex")], text=False, byte_order="<").write(str(path))


def quats_from_frames(u: np.ndarray, v: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Unit quaternions (w, x, y, z) of the rotations whose columns are u, v, w."""
    from scipy.spatial.transform import Rotation
    m = np.stack([u, v, w], axis=2)
    return Rotation.from_matrix(m).as_quat(scalar_first=True)


# ---- similarity transforms as 4 x 4 matrices: M @ [p, 1] = s R p + t ----

def sim3(scale: float, rotation: np.ndarray, translation) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = scale * np.asarray(rotation, float)
    m[:3, 3] = translation
    return m


def split(m: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Scale (always positive), the orthogonal part (a reflection when parity is -1) and the translation."""
    s = float(np.cbrt(abs(np.linalg.det(m[:3, :3]))))
    return s, m[:3, :3] / s, m[:3, 3].copy()


def parity(m: np.ndarray) -> int:
    return 1 if np.linalg.det(np.asarray(m)[:3, :3]) > 0 else -1


def similarity_problem(m, tol: float = 1e-4) -> str | None:
    """None for a proper similarity (uniform scale, rotation, translation, last row 0 0 0 1); else what is wrong.

    A matrix with a reflection is refused: three.js's decompose turns it into a negative scale, which Spark
    draws wrongly (the hallway came out inside the room in review).
    """
    m = np.asarray(m, float)
    if m.shape != (4, 4):
        return f"not 4 x 4 but {m.shape}"
    if not np.isfinite(m).all():
        return "has numbers that are not finite"
    if np.abs(m[3] - [0, 0, 0, 1]).max() > 1e-9:
        return f"last row is {m[3].tolist()}, not [0, 0, 0, 1] (a transposed matrix?)"
    a = m[:3, :3]
    det = np.linalg.det(a)
    if det <= 0:
        return f"determinant {det:.4g} is not positive (a reflection, or degenerate)"
    s2 = det ** (2 / 3)
    if np.abs(a.T @ a - s2 * np.eye(3)).max() > tol * s2:
        return "is not a similarity (columns not orthogonal and of one length)"
    return None


def apply(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ m[:3, :3].T + m[:3, 3]


def invert(m: np.ndarray) -> np.ndarray:
    s, r, t = split(m)
    return sim3(1 / s, r.T, -(r.T @ t) / s)


def column_major(m: np.ndarray) -> list[float]:
    """three.js Matrix4.fromArray order."""
    return [float(round(x, 9)) + 0.0 for x in np.asarray(m, float).T.ravel()]
