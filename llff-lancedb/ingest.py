"""Ingest LLFF scenes into LanceDB.

Reads poses_bounds.npy and indexes camera poses as Plücker coordinate
vectors in LanceDB for nearest-neighbor search.

Usage:
    python ingest.py --data-dir ~/datasets/fork
    python ingest.py --data-dir /tmp/llff_scenes
"""

import sys
from pathlib import Path

import lancedb
import numpy as np
from params_proto import proto

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llff_utils import c2w_to_plucker, parse_llff_poses


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


def ingest_scene(data_dir: Path) -> list[dict]:
    scene_id = data_dir.name

    poses_bounds = np.load(data_dir / "poses_bounds.npy")
    c2w, near_bounds, far_bounds = parse_llff_poses(poses_bounds)
    n_views = len(c2w)
    print(f"  {scene_id}: {n_views} views")

    image_paths = load_image_paths(data_dir)
    if len(image_paths) != n_views:
        raise ValueError(f"Mismatch: {n_views} poses but {len(image_paths)} images")

    plucker = c2w_to_plucker(c2w)

    records = []
    for i in range(n_views):
        records.append({
            "image_path": image_paths[i],
            "camera_pose": plucker[i].tolist(),
            "c2w": c2w[i].flatten().astype(np.float32).tolist(),
            "near": float(near_bounds[i]),
            "far": float(far_bounds[i]),
            "scene_id": scene_id,
            "view_index": i,
        })

    return records


@proto.cli
def main(
    data_dir: str = None,  # Path to LLFF scene dir or parent of multiple scenes
    db_path: str = "./lancedb_data",  # LanceDB directory
    table_name: str = "llff_poses",  # Table name
):
    """Ingest LLFF scenes into LanceDB."""
    if data_dir is None:
        raise SystemExit("--data-dir is required")

    data_dir = Path(data_dir)

    all_records = []
    if (data_dir / "poses_bounds.npy").exists():
        all_records = ingest_scene(data_dir)
    else:
        scene_dirs = sorted(
            d for d in data_dir.iterdir()
            if d.is_dir() and (d / "poses_bounds.npy").exists()
        )
        if not scene_dirs:
            raise SystemExit(f"No LLFF scenes found in {data_dir}")
        print(f"Found {len(scene_dirs)} scenes")
        for d in scene_dirs:
            all_records.extend(ingest_scene(d))

    db = lancedb.connect(db_path)
    table = db.create_table(table_name, all_records, mode="overwrite")
    print(f"Created table '{table_name}' with {len(table)} rows in {db_path}")

    table.create_index("camera_pose", index_type="IVF_PQ", num_partitions=2, num_sub_vectors=2)
    print("Built IVF-PQ index on camera_pose")


if __name__ == "__main__":
    main()
