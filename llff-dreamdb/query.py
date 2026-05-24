"""Query the LLFF dataset for views with similar camera poses.

Given a query camera pose (or an index into the existing dataset),
finds the K nearest views by cosine similarity on the 12-d pose vector.

Usage:
    python query.py --backend http://localhost:9000/examples --top-k 5
    python query.py --backend http://localhost:9000/examples --query-index 3 --top-k 5
"""

import numpy as np
from params_proto import proto

import dreamdb_dataset as vd


@proto.cli
def main(
    backend: str = None,  # DreamDB backend URL
    dataset_name: str = "llff",  # Dataset name
    top_k: int = 5,  # Number of nearest views
    query_index: int = 0,  # Use the pose at this index as the query
):
    """Query LLFF views by camera pose."""
    if backend is None:
        raise SystemExit("--backend is required")

    ds = vd.Dataset.open_ref(dataset_name, backend=backend)
    print(f"Opened dataset '{dataset_name}' ({len(ds)} records)")

    query_pose = None
    for batch in ds.iter_arrow_batches(batch_size=256, fields=["camera_pose"]):
        poses = batch.column("camera_pose").values.to_numpy(zero_copy_only=False)
        poses = poses.reshape(batch.num_rows, 12)
        if query_index < len(poses):
            query_pose = poses[query_index]
            break

    if query_pose is None:
        raise IndexError(f"Query index {query_index} out of range")

    print(f"\nQuery pose (index {query_index}):")
    print(f"  R = {query_pose[:9].reshape(3, 3).round(3)}")
    print(f"  t = {query_pose[9:12].round(3)}")

    print(f"\nTop-{top_k} nearest camera poses:")
    print("-" * 60)

    batches = ds.iter_vector(
        field="camera_pose",
        query=query_pose.tolist(),
        top_k=top_k,
    )

    for batch in batches:
        anchors = batch["_time_anchors"]
        scene_ids = batch["scene_id"]
        view_indices = batch["view_index"]
        for anchor, scene, view in zip(anchors, scene_ids, view_indices):
            print(f"  anchor={anchor}  scene={scene}  view={view}")


if __name__ == "__main__":
    main()
