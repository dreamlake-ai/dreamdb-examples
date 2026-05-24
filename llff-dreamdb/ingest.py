"""Ingest an LLFF scene into DreamDB.

Reads poses_bounds.npy and the corresponding images, then creates
a DreamDB dataset with camera pose vectors indexed for similarity search.

Usage:
    python ingest.py --data-dir data/fern --backend http://localhost:9000/examples
"""

from pathlib import Path

import numpy as np
from params_proto import proto

import dreamdb_dataset as vd


def parse_llff_poses(poses_bounds: np.ndarray):
    poses = poses_bounds[:, :15].reshape(-1, 3, 5)
    c2w = poses[:, :, :4]  # (N, 3, 4) camera-to-world [R|t]
    near = poses_bounds[:, 15]
    far = poses_bounds[:, 16]
    return c2w, near, far


def load_images(data_dir: Path) -> list[Path]:
    for subdir in ["images_4", "images_8", "images"]:
        img_dir = data_dir / subdir
        if img_dir.exists():
            paths = sorted(
                p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            )
            if paths:
                return paths
    raise FileNotFoundError(f"No image directory found in {data_dir}")


@proto.cli
def main(
    data_dir: str = None,  # Path to the LLFF scene directory
    backend: str = None,  # DreamDB backend URL
    dataset_name: str = "llff",  # Dataset name
):
    """Ingest an LLFF scene into DreamDB."""
    if data_dir is None or backend is None:
        raise SystemExit("--data-dir and --backend are required")

    data_dir = Path(data_dir)
    scene_id = data_dir.name

    poses_path = data_dir / "poses_bounds.npy"
    if not poses_path.exists():
        raise FileNotFoundError(f"No poses_bounds.npy in {data_dir}")

    poses_bounds = np.load(poses_path)
    c2w, near_bounds, far_bounds = parse_llff_poses(poses_bounds)
    n_views = len(c2w)
    print(f"Loaded {n_views} camera poses from {poses_path}")

    image_paths = load_images(data_dir)
    if len(image_paths) != n_views:
        raise ValueError(
            f"Mismatch: {n_views} poses but {len(image_paths)} images"
        )

    schema = (
        vd.Schema()
        .add_image("image", mime="jpeg")
        .add_embedding("camera_pose", dim=12, algorithm="dreamdb.lsh-cosine")
        .add_scalar_categorical("scene_id")
        .add_scalar_categorical("view_index")
    )

    ds = vd.Dataset.create(dataset_name, schema, backend=backend)
    print(f"Created dataset '{dataset_name}' on {backend}")

    samples = []
    for i in range(n_views):
        pose_vec = c2w[i].flatten().astype(np.float32)

        with open(image_paths[i], "rb") as f:
            image_bytes = f.read()

        samples.append(
            {
                "image": image_bytes,
                "camera_pose": pose_vec,
                "scene_id": scene_id,
                "view_index": str(i),
            }
        )

    ds.append_many(samples)
    print(f"Ingested {n_views} views from scene '{scene_id}'")

    snapshot = ds.snapshot(f"{scene_id}-initial")
    print(f"Snapshot: {snapshot}")


if __name__ == "__main__":
    main()
