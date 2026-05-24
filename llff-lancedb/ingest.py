"""Ingest an LLFF scene into LanceDB.

Reads poses_bounds.npy and indexes camera poses as vectors in LanceDB
for nearest-neighbor search. Comparable to the DreamDB llff-dreamdb/ingest.py.

Usage:
    python ingest.py --data-dir ../llff-dreamdb/data/synthetic
"""

from pathlib import Path

import lancedb
import numpy as np
from params_proto import proto


def parse_llff_poses(poses_bounds: np.ndarray):
    poses = poses_bounds[:, :15].reshape(-1, 3, 5)
    c2w = poses[:, :, :4]  # (N, 3, 4)
    near = poses_bounds[:, 15]
    far = poses_bounds[:, 16]
    return c2w, near, far


def load_image_paths(data_dir: Path) -> list[str]:
    for subdir in ["images_4", "images_8", "images"]:
        img_dir = data_dir / subdir
        if img_dir.exists():
            paths = sorted(
                str(p)
                for p in img_dir.iterdir()
                if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            )
            if paths:
                return paths
    raise FileNotFoundError(f"No image directory found in {data_dir}")


@proto.cli
def main(
    data_dir: str = None,  # Path to the LLFF scene directory
    db_path: str = "./lancedb_data",  # LanceDB directory
    table_name: str = "llff_poses",  # Table name
):
    """Ingest an LLFF scene into LanceDB."""
    if data_dir is None:
        raise SystemExit("--data-dir is required")

    data_dir = Path(data_dir)
    scene_id = data_dir.name

    poses_bounds = np.load(data_dir / "poses_bounds.npy")
    c2w, near_bounds, far_bounds = parse_llff_poses(poses_bounds)
    n_views = len(c2w)
    print(f"Loaded {n_views} camera poses from {data_dir}")

    image_paths = load_image_paths(data_dir)
    if len(image_paths) != n_views:
        raise ValueError(f"Mismatch: {n_views} poses but {len(image_paths)} images")

    records = []
    for i in range(n_views):
        pose_vec = c2w[i].flatten().astype(np.float32)
        records.append(
            {
                "image_path": image_paths[i],
                "camera_pose": pose_vec.tolist(),
                "near": float(near_bounds[i]),
                "far": float(far_bounds[i]),
                "scene_id": scene_id,
                "view_index": i,
            }
        )

    db = lancedb.connect(db_path)
    table = db.create_table(table_name, records, mode="overwrite")
    print(f"Created table '{table_name}' with {len(table)} rows in {db_path}")

    table.create_index("camera_pose", index_type="IVF_PQ", num_partitions=2, num_sub_vectors=4)
    print("Built IVF-PQ index on camera_pose")


if __name__ == "__main__":
    main()
