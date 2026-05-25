"""Visualize LLFF camera poses using Vuer.

Serves a 3D web viewer showing camera frustums, origins, and images
for LLFF scenes. Open http://localhost:8012 in a browser.

Usage:
    python visualize_llff.py --data-dir ~/datasets/fork
    python visualize_llff.py --data-dir /tmp/llff_scenes
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np
from params_proto import proto

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llff_utils import parse_llff_poses


def load_image_paths(data_dir: Path) -> list[Path]:
    for subdir in ("images", "images_4", "images_8"):
        img_dir = data_dir / subdir
        if img_dir.is_dir():
            paths = sorted(
                p for p in img_dir.iterdir()
                if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
            )
            if paths:
                return paths
    return []


def frustum_lines(c2w: np.ndarray, f: float, w: float, h: float, scale: float = 0.3):
    """Compute the 8 line segments of a camera frustum wireframe."""
    hw, hh = w / (2 * f) * scale, h / (2 * f) * scale
    corners_local = np.array([
        [0, 0, 0],
        [-hw, -hh, scale],
        [hw, -hh, scale],
        [hw, hh, scale],
        [-hw, hh, scale],
    ])
    R, t = c2w[:3, :3], c2w[:3, 3]
    corners_world = (R @ corners_local.T).T + t

    o, tl, tr, br, bl = corners_world
    edges = [
        [o, tl], [o, tr], [o, br], [o, bl],
        [tl, tr], [tr, br], [br, bl], [bl, tl],
    ]
    return edges


def load_scene(data_dir: Path):
    poses_bounds = np.load(data_dir / "poses_bounds.npy")
    c2ws, hwfs, bounds = parse_llff_poses(poses_bounds)
    image_paths = load_image_paths(data_dir)
    return c2ws, hwfs, bounds, image_paths


@proto.cli
def main(
    data_dir: str = None,  # Path to LLFF scene dir or parent of multiple scenes
    port: int = 8012,  # Server port
    frustum_scale: float = 0.3,  # Camera frustum display scale
):
    """Visualize LLFF camera poses with Vuer."""
    if data_dir is None:
        raise SystemExit("--data-dir is required")

    from vuer import Vuer, VuerSession
    from vuer.schemas import CoordsMarker, Line, PointCloud, group, Scene, AmbientLight

    data_dir = Path(data_dir)

    scenes = {}
    if (data_dir / "poses_bounds.npy").exists():
        scenes[data_dir.name] = load_scene(data_dir)
    else:
        for d in sorted(data_dir.iterdir()):
            if d.is_dir() and (d / "poses_bounds.npy").exists():
                scenes[d.name] = load_scene(d)

    if not scenes:
        raise SystemExit(f"No LLFF scenes found in {data_dir}")

    print(f"Loaded {len(scenes)} scene(s): {', '.join(scenes.keys())}")

    app = Vuer(port=port)

    @app.spawn(start=True)
    async def handler(session: VuerSession):
        await asyncio.sleep(0.5)

        for scene_name, (c2ws, hwfs, bounds, image_paths) in scenes.items():
            n_views = len(c2ws)
            prefix = scene_name

            positions = c2ws[:, :3, 3].astype(np.float32)
            session.upsert @ PointCloud(
                vertices=positions,
                key=f"{prefix}/origins",
                size=3,
                color="cyan",
            )

            for i in range(n_views):
                h, w, f = hwfs[i]
                edges = frustum_lines(c2ws[i], f, w, h, scale=frustum_scale)
                for j, (start, end) in enumerate(edges):
                    session.upsert @ Line(
                        points=[start.tolist(), end.tolist()],
                        key=f"{prefix}/frustum_{i:03d}/edge_{j}",
                        color="orange" if j < 4 else "white",
                        lineWidth=1,
                    )

            print(f"  {scene_name}: {n_views} camera frustums")

        print(f"Serving at http://localhost:{port}")

        while True:
            await asyncio.sleep(1.0)

    app.run()


if __name__ == "__main__":
    main()
