"""Ingest LLFF scenes into DreamDB.

Reads poses_bounds.npy and the corresponding images, then creates
a DreamDB dataset with Plücker coordinate vectors indexed for similarity search.

Usage:
    python ingest.py --data-dir ~/datasets/fork --backend http://localhost:9000/examples
    python ingest.py --data-dir /tmp/llff_scenes --backend http://localhost:9000/examples
"""

import sys
from pathlib import Path

import numpy as np
from params_proto import proto

import dreamdb_dataset as vd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llff_utils import c2w_to_plucker, parse_llff_poses


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


def ingest_scene(data_dir: Path, ds):
    scene_id = data_dir.name

    poses_bounds = np.load(data_dir / "poses_bounds.npy")
    c2w, near_bounds, far_bounds = parse_llff_poses(poses_bounds)
    n_views = len(c2w)
    print(f"  {scene_id}: {n_views} views")

    image_paths = load_images(data_dir)
    if len(image_paths) != n_views:
        raise ValueError(f"Mismatch: {n_views} poses but {len(image_paths)} images")

    plucker = c2w_to_plucker(c2w)

    samples = []
    for i in range(n_views):
        with open(image_paths[i], "rb") as f:
            image_bytes = f.read()

        samples.append({
            "image": image_bytes,
            "camera_pose": plucker[i],
            "c2w": c2w[i].flatten().astype(np.float32),
            "near": float(near_bounds[i]),
            "far": float(far_bounds[i]),
            "scene_id": scene_id,
            "view_index": str(i),
        })

    ds.append_many(samples)
    print(f"    ingested {n_views} views")


@proto.cli
def main(
    data_dir: str = None,  # Path to LLFF scene dir or parent of multiple scenes
    backend: str = None,  # DreamDB backend URL
    dataset_name: str = "llff",  # Dataset name
):
    """Ingest LLFF scenes into DreamDB."""
    if data_dir is None or backend is None:
        raise SystemExit("--data-dir and --backend are required")

    data_dir = Path(data_dir)

    schema = (
        vd.Schema()
        .add_image("image", mime="jpeg")
        .add_embedding("camera_pose", dim=6, algorithm="dreamdb.lsh-cosine")
        .add_embedding("c2w", dim=12, algorithm="dreamdb.lsh-cosine")
        .add_scalar_categorical("scene_id")
        .add_scalar_categorical("view_index")
    )

    ds = vd.Dataset.create(dataset_name, schema, backend=backend)
    print(f"Created dataset '{dataset_name}' on {backend}")

    if (data_dir / "poses_bounds.npy").exists():
        ingest_scene(data_dir, ds)
    else:
        scene_dirs = sorted(
            d for d in data_dir.iterdir()
            if d.is_dir() and (d / "poses_bounds.npy").exists()
        )
        if not scene_dirs:
            raise SystemExit(f"No LLFF scenes found in {data_dir}")
        print(f"Found {len(scene_dirs)} scenes")
        for d in scene_dirs:
            ingest_scene(d, ds)

    snapshot = ds.snapshot(f"{dataset_name}-initial")
    print(f"Snapshot: {snapshot}")


if __name__ == "__main__":
    main()
