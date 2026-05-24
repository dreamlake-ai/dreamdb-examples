# LLFF Camera Pose Index (DreamDB)

Index [LLFF](https://github.com/Fyusion/LLFF) scenes in DreamDB so you can search for views by camera pose similarity.

Each record stores the camera's principal ray as a 6-d [Plücker coordinate](https://en.wikipedia.org/wiki/Pl%C3%BCcker_coordinates) for vector similarity search, plus the source image and depth bounds.

## What This Does

1. **Ingest** — Reads `poses_bounds.npy`, converts each camera-to-world matrix to Plücker coordinates, and appends everything to a DreamDB dataset.
2. **Query** — Given a query camera pose, retrieves the K nearest views by cosine similarity on the Plücker vectors.
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

## Dependencies

```bash
pip install dreamdb-dataset params-proto numpy Pillow
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `image` | image/jpeg | Source view (downsampled if `images_4/` exists) |
| `camera_pose` | embedding(6) | Plücker coordinate `[d | m]` of the principal ray |
| `scene_id` | categorical | Scene name (e.g. `"fern"`) |
| `view_index` | categorical | View index within the scene |

## Plücker Coordinates

LLFF stores camera poses as `(N, 17)` arrays. We extract the 3×4 camera-to-world matrix and convert to Plücker coordinates:

```
Camera-to-world [R|t] → Plücker (d, m)

  d = -R[:, 2]          # viewing direction (negative z-axis)
  m = t × d             # moment = position × direction
  plücker = [d | m]     # 6-d vector
```

Cosine similarity on Plücker coordinates finds views with similar viewing direction **and** position — geometrically meaningful for camera retrieval.
