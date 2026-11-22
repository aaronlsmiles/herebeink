import numpy as np
import pytest
from plyfile import PlyData
from scipy.spatial.transform import Rotation

import splats


def test_sim3_apply_invert_and_split():
    r = Rotation.from_euler("xyz", [10, 20, 30], degrees=True).as_matrix()
    m = splats.sim3(2.5, r, [1.0, -2.0, 0.5])
    p = np.array([[0.1, 0.2, 0.3], [1.0, 0.0, -1.0]])
    assert splats.apply(m, p) == pytest.approx(2.5 * p @ r.T + [1.0, -2.0, 0.5])
    assert splats.apply(splats.invert(m), splats.apply(m, p)) == pytest.approx(p)
    s, r2, t = splats.split(m)
    assert s == pytest.approx(2.5) and r2 == pytest.approx(r) and t == pytest.approx([1.0, -2.0, 0.5])


def test_column_major_is_three_js_order():
    m = splats.sim3(1.0, np.eye(3), [7.0, 8.0, 9.0])
    assert splats.column_major(m)[12:15] == [7.0, 8.0, 9.0]


def test_write_read_and_subset_keep_everything(tmp_path):
    rng = np.random.default_rng(0)
    xyz = rng.random((50, 3))
    n = np.tile([0.0, 0.0, 1.0], (50, 1))
    u = np.tile([1.0, 0.0, 0.0], (50, 1))
    splats.write_splats(tmp_path / "a.ply", xyz, rng.random((50, 3)), n, u, size=0.01)
    ply = splats.read(tmp_path / "a.ply")
    assert splats.count(tmp_path / "a.ply") == 50
    assert splats.centres(ply) == pytest.approx(xyz, abs=1e-6)
    assert splats.opacity(ply) == pytest.approx(0.95, abs=1e-6)
    # a comment written into the file, as a source's provenance note would be
    PlyData([ply["vertex"]], text=False, byte_order="<", comments=["provenance: kept"]).write(str(tmp_path / "c.ply"))
    ply = splats.read(tmp_path / "c.ply")
    keep = np.arange(50) % 3 == 0
    assert splats.write_subset(ply, keep, tmp_path / "b.ply") == 17
    sub = PlyData.read(str(tmp_path / "b.ply"))
    assert sub.comments == ["provenance: kept"]
    assert sub["vertex"].data.dtype == ply["vertex"].data.dtype
    assert np.array_equal(sub["vertex"].data, ply["vertex"].data[keep])


def test_surface_frame_quaternions():
    q = splats.quats_from_frames(np.array([[1.0, 0, 0]]), np.array([[0, 1.0, 0]]), np.array([[0, 0, 1.0]]))
    assert q[0] == pytest.approx([1, 0, 0, 0])


# ---- reading unexpected files, and baking a mirror into a file ----

C1 = 0.4886025119029199
C2 = [1.0925484305920792, -1.0925484305920792, 0.31539156525252005, -1.0925484305920792, 0.5462742152960396]
C3 = [-0.5900435899266435, 2.890611442640554, -0.4570457994644658, 0.3731763325901154, -0.4570457994644658,
      1.445305721320277, -0.5900435899266435]


def sh_basis(d):
    """The real SH basis for degrees 1 to 3 in the order 3DGS (and Spark) store f_rest, as in 3DGS's eval_sh."""
    x, y, z = d[:, 0], d[:, 1], d[:, 2]
    xx, yy, zz = x * x, y * y, z * z
    return np.stack([
        -C1 * y, C1 * z, -C1 * x,
        C2[0] * x * y, C2[1] * y * z, C2[2] * (2 * zz - xx - yy), C2[3] * x * z, C2[4] * (xx - yy),
        C3[0] * y * (3 * xx - yy), C3[1] * x * y * z, C3[2] * y * (4 * zz - xx - yy), C3[3] * z * (2 * zz - 3 * xx - 3 * yy),
        C3[4] * x * (4 * zz - xx - yy), C3[5] * z * (xx - yy), C3[6] * x * (xx - 3 * yy)], axis=1)


def sh_ply(path, n=200, degree=3, seed=0):
    from plyfile import PlyElement
    rng = np.random.default_rng(seed)
    k = (degree + 1) ** 2 - 1
    names = (["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"] + [f"f_rest_{i}" for i in range(3 * k)]
             + ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"])
    arr = np.zeros(n, dtype=[(m, "<f4") for m in names])
    for m in names:
        arr[m] = rng.normal(size=n)
    q = Rotation.random(n, random_state=seed).as_quat(scalar_first=True)
    for i in range(4):
        arr[f"rot_{i}"] = q[:, i] * 1.7  # files store unnormalised quaternions
    PlyData([PlyElement.describe(arr, "vertex")], text=False, byte_order="<", comments=["kept"]).write(str(path))
    return splats.read(path, quiet=True)


def test_describe_names_properties_sh_degree_and_opacity(tmp_path):
    ply = sh_ply(tmp_path / "a.ply", degree=3)
    text = splats.describe(ply, "a.ply")
    assert "200 splats" in text and "SH degree 3" in text and "opacity" in text and "f_rest_44" in text
    assert splats.sh_degree(ply) == 3
    assert splats.sh_degree(sh_ply(tmp_path / "b.ply", degree=1)) == 1


def test_a_compressed_or_odd_ply_is_refused_in_words(tmp_path):
    from plyfile import PlyElement
    chunk = np.zeros(2, dtype=[("min_x", "<f4")])
    packed = np.zeros(5, dtype=[("packed_position", "<u4"), ("packed_rotation", "<u4")])
    PlyData([PlyElement.describe(chunk, "chunk"), PlyElement.describe(packed, "vertex")]).write(str(tmp_path / "c.ply"))
    with pytest.raises(splats.PlyFormatError, match="compressed"):
        splats.read(tmp_path / "c.ply", quiet=True)
    odd = np.zeros(3, dtype=[("a", "<f4")])
    PlyData([PlyElement.describe(odd, "vertex")]).write(str(tmp_path / "d.ply"))
    with pytest.raises(splats.PlyFormatError, match="no x, y, z"):
        splats.read(tmp_path / "d.ply", quiet=True)


def test_other_elements_are_named_as_dropped(tmp_path, capsys):
    from plyfile import PlyElement
    ply = sh_ply(tmp_path / "a.ply", degree=0)
    faces = np.zeros(2, dtype=[("k", "<i4")])
    PlyData([ply["vertex"], PlyElement.describe(faces, "extra")]).write(str(tmp_path / "e.ply"))
    splats.read(tmp_path / "e.ply")
    assert "extra (2) is dropped" in capsys.readouterr().out


def test_sh_coefficients_odd_in_x_are_the_ones_the_basis_says():
    rng = np.random.default_rng(1)
    d = rng.normal(size=(500, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    flip = np.ones(15)
    flip[list(splats.SH_ODD_IN_X)] = -1
    assert sh_basis(d * [-1, 1, 1]) == pytest.approx(sh_basis(d) * flip, abs=1e-12)


@pytest.mark.parametrize("degree", [0, 1, 2, 3])
def test_mirror_bake_keeps_every_splat_as_seen_from_the_mirrored_side(tmp_path, degree):
    ply = sh_ply(tmp_path / "a.ply", degree=degree)
    src = ply["vertex"].data
    out = splats.mirror_x(src)
    k = (degree + 1) ** 2 - 1
    assert out["x"] == pytest.approx(-src["x"]) and out["y"] == pytest.approx(src["y"]) and out["nx"] == pytest.approx(-src["nx"])
    rng = np.random.default_rng(2)
    d = rng.normal(size=(len(src), 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    for c in range(3 if k else 0):
        coef = lambda a: np.stack([a[f"f_rest_{c * k + i}"] for i in range(k)], 1).astype(float)  # noqa: E731
        before = (coef(src) * sh_basis(d)[:, :k]).sum(1)
        after = (coef(out) * sh_basis(d * [-1, 1, 1])[:, :k]).sum(1)
        assert after == pytest.approx(before, abs=1e-5)
    # the Gaussian's shape: covariance R S^2 R^T must come out as Mx Sigma Mx
    q0 = np.stack([src[f"rot_{i}"] for i in range(4)], 1).astype(float)
    q1 = np.stack([out[f"rot_{i}"] for i in range(4)], 1).astype(float)
    s = np.exp(np.stack([src[f"scale_{i}"] for i in range(3)], 1).astype(float))
    r0 = Rotation.from_quat(q0, scalar_first=True).as_matrix()
    r1 = Rotation.from_quat(q1, scalar_first=True).as_matrix()
    mx = np.diag([-1.0, 1, 1])
    cov0 = r0 @ (s[:, :, None] ** 2 * np.eye(3)) @ r0.transpose(0, 2, 1)
    cov1 = r1 @ (s[:, :, None] ** 2 * np.eye(3)) @ r1.transpose(0, 2, 1)
    assert cov1 == pytest.approx(mx @ cov0 @ mx, abs=1e-6)


def test_similarity_check():
    r = Rotation.from_euler("xyz", [10, 20, 30], degrees=True).as_matrix()
    assert splats.similarity_problem(splats.sim3(2.0, r, [1, 2, 3])) is None
    assert "determinant" in splats.similarity_problem(splats.sim3(2.0, r @ np.diag([-1.0, 1, 1]), [0, 0, 0]))
    squash = splats.sim3(1.0, r, [0, 0, 0])
    squash[:3, 0] *= 1.1
    assert "similarity" in splats.similarity_problem(squash)
    bad = np.eye(4)
    bad[3, 0] = 0.5
    assert "last row" in splats.similarity_problem(bad)
    assert "finite" in splats.similarity_problem(np.full((4, 4), np.nan))
    m = splats.sim3(-1.0, np.eye(3), [0, 0, 0])
    assert splats.split(m)[0] == pytest.approx(1.0) and splats.parity(m) == -1
