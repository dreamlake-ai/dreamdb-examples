# LLFF Camera Pose Index

Index [LLFF](https://github.com/Fyusion/LLFF) scenes in DreamDB so you can search for views by camera pose similarity.

Each record stores a flattened camera-to-world matrix (12-d) as an embedding vector, plus the scene depth bounds and a reference to the source image.

## What This Does

1. **Ingest** — Reads `poses_bounds.npy`, pairs each pose with the corresponding image, and appends everything to a DreamDB dataset.
2. **Query** — Given a query camera pose, retrieves the K nearest views by cosine similarity on the pose vectors.
3. **Synthetic data** — `generate_synthetic.py` creates a small synthetic scene for testing without downloading real data.

## Quick Start

```bash
# Generate a synthetic LLFF scene
python generate_synthetic.py

# Ingest into DreamDB
python ingest.py --data-dir data/synthetic --backend http://localhost:9000/examples

# Query for nearest camera poses
python query.py --backend http://localhost:9000/examples --top-k 5
```

## Using Real LLFF Data

Download a scene from the [LLFF dataset](https://drive.google.com/drive/folders/128yBriW1IG_3NJ5Rp7APSTZsJqdJdfc1):

```bash
# Example: the "fern" scene
unzip fern.zip -d data/fern

python ingest.py --data-dir data/fern --backend http://localhost:9000/examples
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `image` | image/jpeg | Source view (downsampled if `images_4/` exists) |
| `camera_pose` | embedding(12) | Flattened 3×4 camera-to-world `[R|t]` matrix |
| `near` | float | Near depth bound |
| `far` | float | Far depth bound |
| `scene_id` | categorical | Scene name (e.g. `"fern"`) |
| `view_index` | categorical | View index within the scene |

## Camera Pose Convention

LLFF stores poses as `(N, 17)` arrays in `poses_bounds.npy`:

```
[ r11 r12 r13 t1 ]
[ r21 r22 r23 t2 ]   +  [ h w f ]  +  [ near far ]
[ r31 r32 r33 t3 ]
 ─── 3×4 c2w ────     hwf (ignored)    depth bounds
     (12 values)       (3 values)       (2 values)
```

We index the 12-element `[R|t]` as the embedding vector. This captures both camera position and orientation, so nearest-neighbor search finds views with similar viewpoints.
