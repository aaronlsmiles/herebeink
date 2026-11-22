import numpy as np
import open3d as o3d
import plyfile
import scipy.spatial


def test_environment_imports_and_kdtree():
    assert plyfile.PlyData is not None
    pts = np.array([[0.0, 0, 0], [1, 0, 0], [0, 2, 0]])
    _, idx = scipy.spatial.cKDTree(pts).query([0.9, 0.1, 0])
    assert idx == 1

    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pts))
    _, found, _ = o3d.geometry.KDTreeFlann(pcd).search_knn_vector_3d([0, 1.9, 0], 1)
    assert list(found) == [2]
