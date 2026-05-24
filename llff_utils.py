"""Shared utilities for LLFF examples."""

import numpy as np


def parse_llff_poses(poses_bounds: np.ndarray):
    """Parse LLFF poses_bounds (N, 17) into c2w matrices and depth bounds."""
    poses = poses_bounds[:, :15].reshape(-1, 3, 5)
    # LLFF R columns are [down, right, backwards].
    # Convert to NeRF convention [right, up, backwards] (OpenGL-style).
    c2w = poses[:, :, [1, 0, 2, 3]]  # [right, down, backwards, t]
    c2w[:, :, 1] *= -1  # down → up → [right, up, backwards, t]
    near = poses_bounds[:, 15]
    far = poses_bounds[:, 16]
    return c2w, near, far


def c2w_to_plucker(c2w: np.ndarray) -> np.ndarray:
    """Convert camera-to-world matrices to Plücker coordinates.

    For each camera, computes the Plücker representation of its
    principal viewing ray: (d, m) where d is the viewing direction
    and m = t × d is the moment vector.

    Args:
        c2w: (N, 3, 4) or (3, 4) camera-to-world matrices.

    Returns:
        (N, 6) or (6,) Plücker coordinates [d | m].
    """
    squeeze = c2w.ndim == 2
    if squeeze:
        c2w = c2w[None]

    # Viewing direction: -Z in NeRF/OpenGL convention (camera looks along -Z)
    d = -c2w[:, :3, 2]  # (N, 3)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)

    # Camera position
    t = c2w[:, :3, 3]  # (N, 3)

    # Moment: m = t × d
    m = np.cross(t, d)  # (N, 3)

    plucker = np.concatenate([d, m], axis=1).astype(np.float32)  # (N, 6)
    return plucker[0] if squeeze else plucker
