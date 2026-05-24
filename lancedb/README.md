# LanceDB Camera Pose Index

Same LLFF camera pose indexing use case as the [`../llff/`](../llff/) example, but using [LanceDB](https://lancedb.github.io/lancedb/) as the vector store for comparison.

LanceDB is an embedded vector database (no server needed) that stores data in Lance columnar format. This example shows the equivalent workflow side-by-side with the DreamDB version.

## Quick Start

```bash
# Generate synthetic data (shared with the LLFF example)
cd ../llff && python generate_synthetic.py && cd ../lancedb

# Ingest into LanceDB
python ingest.py --data-dir ../llff/data/synthetic

# Query for nearest camera poses
python query.py --top-k 5
```

## Dependencies

```bash
pip install lancedb numpy pyarrow Pillow
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| `image_path` | string | Path to the source image |
| `camera_pose` | vector(12) | Flattened 3×4 camera-to-world `[R\|t]` matrix |
| `near` | float32 | Near depth bound |
| `far` | float32 | Far depth bound |
| `scene_id` | string | Scene name |
| `view_index` | int32 | View index within the scene |

## Key Differences from DreamDB

| | DreamDB | LanceDB |
|---|---------|---------|
| Architecture | Client-server | Embedded (in-process) |
| Storage | S3-native, append-only log | Local Lance files |
| Versioning | Built-in snapshots + branches | Implicit versioning via Lance |
| Image storage | Inline blobs | Paths (images stored externally) |
| Index type | LSH / IVF / IMI | IVF-PQ (auto-built) |
| Streaming | Arrow batch streaming | PyArrow table scans |
