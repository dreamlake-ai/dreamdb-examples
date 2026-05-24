"""Generate a synthetic LLFF scene for testing.

Creates camera poses arranged on a hemisphere looking at the origin,
plus placeholder JPEG images. The output matches the LLFF directory
layout expected by ingest.py.
"""

import argparse
import os

import numpy as np


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Build a 3x4 camera-to-world matrix from eye, target, and up."""
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    c2w = np.eye(4, dtype=np.float32)[:3]
    c2w[:, 0] = right
    c2w[:, 1] = true_up
    c2w[:, 2] = -forward
    c2w[:, 3] = eye
    return c2w


def make_placeholder_jpeg(width: int = 64, height: int = 64) -> bytes:
    """Create a minimal solid-color JPEG without PIL."""
    try:
        from PIL import Image
        import io

        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        return buf.getvalue()
    except ImportError:
        raise SystemExit(
            "Pillow is required to generate placeholder images.\n"
            "Install it with: pip install Pillow"
        )


def generate_hemisphere_poses(
    n_views: int = 20,
    radius: float = 4.0,
    near: float = 0.5,
    far: float = 8.0,
) -> np.ndarray:
    """Generate camera poses on a hemisphere, returned as (N, 17) LLFF format."""
    up = np.array([0.0, 0.0, 1.0])
    target = np.zeros(3)

    poses_bounds = []
    for i in range(n_views):
        theta = 2 * np.pi * i / n_views
        phi = np.pi / 4 + np.random.uniform(-0.2, 0.2)
        x = radius * np.cos(theta) * np.sin(phi)
        y = radius * np.sin(theta) * np.sin(phi)
        z = radius * np.cos(phi)
        eye = np.array([x, y, z], dtype=np.float32)

        c2w = look_at(eye, target, up)
        hwf = np.array([64.0, 64.0, 50.0], dtype=np.float32)

        # LLFF layout: [3x5 matrix flattened in column-major, near, far]
        pose_hwf = np.concatenate([c2w, hwf[:, None]], axis=1)  # (3, 5)
        row = np.concatenate([pose_hwf.ravel(order="F"), [near, far]])
        poses_bounds.append(row)

    return np.array(poses_bounds, dtype=np.float64)


def main():
    parser = argparse.ArgumentParser(description="Generate a synthetic LLFF scene")
    parser.add_argument(
        "--output-dir",
        default="data/synthetic",
        help="Output directory (default: data/synthetic)",
    )
    parser.add_argument(
        "--n-views", type=int, default=20, help="Number of views (default: 20)"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    np.random.seed(args.seed)
    out = os.path.join(os.path.dirname(__file__), args.output_dir)
    img_dir = os.path.join(out, "images")
    os.makedirs(img_dir, exist_ok=True)

    poses_bounds = generate_hemisphere_poses(n_views=args.n_views)
    np.save(os.path.join(out, "poses_bounds.npy"), poses_bounds)

    for i in range(args.n_views):
        jpeg_bytes = make_placeholder_jpeg()
        with open(os.path.join(img_dir, f"image_{i:03d}.jpg"), "wb") as f:
            f.write(jpeg_bytes)

    print(f"Created {args.n_views} views in {out}/")
    print(f"  poses_bounds.npy  shape: {poses_bounds.shape}")
    print(f"  images/           count: {args.n_views}")


if __name__ == "__main__":
    main()
