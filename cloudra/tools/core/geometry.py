"""共享几何原语（纯函数，无 RDKit 依赖）：旋转、取向采样与 Kabsch RMSD。

抽成模块级公开原语的唯一理由：`conformer_search` 的系综去重与
`complex_assembly` 的组装候选去重必须用**同一套**几何比较，不能各写一份
（RMSD 阈值 0.5 Å 已经由用户批准的组装参数与构象搜索默认值共同使用）。
"""

from __future__ import annotations

import math


def kabsch_rmsd(pos_a, pos_b) -> float:
    """两个坐标集（各自先去质心）的 Kabsch 最优 RMSD。"""
    import numpy as np

    a = np.asarray(pos_a, dtype=float)
    b = np.asarray(pos_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError(f"kabsch_rmsd needs equal shapes, got {a.shape} and {b.shape}")
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    cov = a.T @ b
    v, _, wt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(v @ wt))
    rot = v @ np.diag([1.0, 1.0, d]) @ wt
    diff = a @ rot - b
    return float(math.sqrt(float((diff ** 2).sum()) / len(a)))


def fibonacci_sphere_directions(count: int) -> list[tuple[float, float, float]]:
    """单位球面上近似均匀的 ``count`` 个方向（斐波那契球面）。

    确定性、无随机数：同一 ``count`` 永远给出同一组方向，因此组装取向采样可复现。
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if count == 1:
        return [(0.0, 0.0, 1.0)]
    golden = math.pi * (3.0 - math.sqrt(5.0))
    directions: list[tuple[float, float, float]] = []
    for index in range(count):
        y = 1.0 - 2.0 * index / (count - 1)
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * index
        directions.append((math.cos(theta) * radius, y, math.sin(theta) * radius))
    return directions


def rotation_matrix_between(source, target):
    """把单位向量 ``source`` 旋到单位向量 ``target`` 的 3×3 旋转矩阵（Rodrigues）。

    平行（同向/反向）时返回单位阵或 180° 旋转，不做除零。
    """
    import numpy as np

    a = np.asarray(source, dtype=float)
    b = np.asarray(target, dtype=float)
    n_a, n_b = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if n_a < 1e-12 or n_b < 1e-12:
        raise ValueError("rotation_matrix_between needs non-zero vectors")
    a, b = a / n_a, b / n_b
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))
    if s < 1e-12:
        if c > 0.0:
            return np.eye(3)
        # 反向：绕任一正交轴转 180°
        helper = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(a, helper))) > 0.9:
            helper = np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, helper)
        axis = axis / float(np.linalg.norm(axis))
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    vx = np.array([
        [0.0, -v[2], v[1]],
        [v[2], 0.0, -v[0]],
        [-v[1], v[0], 0.0],
    ])
    return np.eye(3) + vx + vx @ vx * ((1.0 - c) / (s * s))


def rotate_about_centroid(positions, atom_indices, rotation):
    """把 ``atom_indices`` 这些原子绕其质心做刚体旋转（片内几何保持不变）。"""
    import numpy as np

    positions = np.asarray(positions, dtype=float)
    out = positions.copy()
    block = positions[list(atom_indices)]
    centroid = block.mean(axis=0)
    out[list(atom_indices)] = (block - centroid) @ np.asarray(rotation, dtype=float).T + centroid
    return out


def min_distance(positions, group_a, group_b) -> float:
    """两组原子之间的最小原子间距。"""
    import numpy as np

    positions = np.asarray(positions, dtype=float)
    a = positions[list(group_a)]
    b = positions[list(group_b)]
    diff = a[:, None, :] - b[None, :, :]
    return float(np.sqrt((diff ** 2).sum(axis=2)).min())
