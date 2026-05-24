#!/usr/bin/env python3
"""Convert LLFF scenes to Rerun (.rrd) and LanceDB formats.

Each scene gets a single camera entity whose pose and image change
over the "frame" timeline — scrub the timeline to step through views.

LLFF pose format (N, 17):
  The first 15 values are a 3x5 matrix [R | t | hwf] stored row-major.
  R columns are [down, right, backwards] in world space.
  Last 2 values are [near, far] depth bounds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from params_proto import proto


def parse_llff_poses(poses_bounds: np.ndarray):
    assert poses_bounds.shape[1] == 17, (
        f"Expected 17 columns, got {poses_bounds.shape[1]}"
    )
    poses = poses_bounds[:, :15].reshape(-1, 3, 5)
    hwfs = poses[:, :, 4]  # (N, 3) — [height, width, focal_length]

    # LLFF R columns are [down, right, backwards].
    # Rerun Pinhole expects c2w columns = [right, down, forward].
    c2ws = poses[:, :, [1, 0, 2, 3]]  # [right, down, backwards, t]
    c2ws[:, :, 2] *= -1  # backwards → forward → [right, down, forward, t]
    bounds = poses_bounds[:, 15:17]  # (N, 2) — [near, far]
    return c2ws, hwfs, bounds


def load_images(data_dir: Path) -> list[tuple[str, np.ndarray]] | None:
    try:
        from PIL import Image as PILImage
    except ImportError:
        print("Pillow not installed — skipping image loading.", file=sys.stderr)
        return None

    for subdir in ("images", "images_4", "images_8"):
        img_dir = data_dir / subdir
        if img_dir.is_dir():
            break
    else:
        return None

    extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
    paths = sorted(
        p for p in img_dir.iterdir() if p.suffix.lower() in extensions
    )
    if not paths:
        return None

    images = []
    for p in paths:
        img = PILImage.open(p)
        images.append((p.name, np.asarray(img)))

    return images


def load_image_paths(data_dir: Path) -> list[str]:
    for subdir in ("images", "images_4", "images_8"):
        img_dir = data_dir / subdir
        if img_dir.is_dir():
            break
    else:
        return []

    extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
    return sorted(str(p) for p in img_dir.iterdir() if p.suffix.lower() in extensions)


def c2w_to_plucker(c2w: np.ndarray) -> np.ndarray:
    """Convert c2w matrices (already in [right, down, forward] convention) to Plücker coords."""
    squeeze = c2w.ndim == 2
    if squeeze:
        c2w = c2w[None]
    d = c2w[:, :3, 2]  # forward = +Z column (already forward after our reorder)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    t = c2w[:, :3, 3]
    m = np.cross(t, d)
    plucker = np.concatenate([d, m], axis=1).astype(np.float32)
    return plucker[0] if squeeze else plucker


def convert_scene(scene_name: str, data_dir: Path, output_dir: Path, no_images: bool, spawn: bool):
    poses_path = data_dir / "poses_bounds.npy"
    if not poses_path.exists():
        print(f"Skipping {scene_name}: no poses_bounds.npy", file=sys.stderr)
        return

    poses_bounds = np.load(poses_path)
    c2ws, hwfs, bounds = parse_llff_poses(poses_bounds)
    n_views = len(c2ws)

    images = None
    if not no_images:
        images = load_images(data_dir)

    print(f"  {scene_name}: {n_views} views" + (f", {len(images)} images" if images else ""))

    # --- Rerun .rrd ---
    import rerun as rr

    rrd_path = output_dir / f"{scene_name}.rrd"
    rr.init(f"llff/{scene_name}")

    sinks = [rr.FileSink(str(rrd_path))]
    if spawn:
        rr.spawn()
        sinks.append(rr.GrpcSink())
    rr.set_sinks(*sinks)

    rr.log("world", rr.ViewCoordinates.RIGHT_HAND_Y_UP, static=True)

    camera_positions = c2ws[:, :3, 3]
    rr.log("world/origins", rr.Points3D(camera_positions, radii=0.02), static=True)

    h, w, f = hwfs[0]
    rr.log("world/camera/image", rr.Pinhole(
        focal_length=float(f), width=int(w), height=int(h),
    ), static=True)

    for i in range(n_views):
        rr.set_time("frame", sequence=i)

        R = c2ws[i, :3, :3]
        t = c2ws[i, :3, 3]

        rr.log("world/camera", rr.Transform3D(mat3x3=R, translation=t))
        rr.log("world/active", rr.Points3D([t], radii=0.05, colors=[[255, 0, 0]]))

        if images is not None and i < len(images):
            _name, img_array = images[i]
            rr.log("world/camera/image", rr.Image(img_array))

    print(f"    saved {rrd_path}")

    # --- LanceDB ---
    import lancedb

    db_path = output_dir / f"{scene_name}.lance"
    plucker = c2w_to_plucker(c2ws)
    image_paths = load_image_paths(data_dir)

    records = []
    for i in range(n_views):
        records.append({
            "image_path": image_paths[i] if i < len(image_paths) else "",
            "camera_pose": plucker[i].tolist(),
            "c2w": c2ws[i].flatten().tolist(),
            "near": float(bounds[i, 0]),
            "far": float(bounds[i, 1]),
            "scene_id": scene_name,
            "view_index": i,
        })

    db = lancedb.connect(str(db_path))
    table = db.create_table("cameras", records, mode="overwrite")
    print(f"    saved {db_path} ({len(table)} rows)")

    near_min, far_max = bounds[:, 0].min(), bounds[:, 1].max()
    print(f"    depth bounds: near={near_min:.3f}, far={far_max:.3f}")


@proto.cli
def main(
    data_dir: str = None,  # Path to LLFF scene dir or parent of multiple scenes
    output_dir: str = "./output",  # Output directory for .rrd and .lance files
    no_images: bool = False,  # Skip loading source images
    spawn: bool = True,  # Open the Rerun viewer
):
    """Convert LLFF scenes to Rerun and LanceDB formats."""
    if data_dir is None:
        raise SystemExit("--data-dir is required")

    try:
        import rerun as rr
        import lancedb
    except ImportError as e:
        raise SystemExit(f"Missing dependency: {e}\n  pip install rerun-sdk lancedb")

    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if (data_dir / "poses_bounds.npy").exists():
        convert_scene(data_dir.name, data_dir, output_dir, no_images, spawn)
    else:
        scene_dirs = sorted(
            d for d in data_dir.iterdir()
            if d.is_dir() and (d / "poses_bounds.npy").exists()
        )
        if not scene_dirs:
            raise SystemExit(f"No LLFF scenes found in {data_dir}")
        print(f"Found {len(scene_dirs)} scenes in {data_dir}")
        for d in scene_dirs:
            convert_scene(d.name, d, output_dir, no_images, spawn)

    print("Done.")


if __name__ == "__main__":
    main()
