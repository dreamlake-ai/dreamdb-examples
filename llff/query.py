"""Query the LLFF dataset for views with similar camera poses.

Given a query camera pose (or an index into the existing dataset),
finds the K nearest views by cosine similarity on the 12-d pose vector.

Usage:
    python query.py --backend http://localhost:9000/examples --top-k 5
    python query.py --backend http://localhost:9000/examples --query-index 3 --top-k 5
"""

import argparse

import numpy as np

import dreamdb_dataset as vd


def main():
    parser = argparse.ArgumentParser(description="Query LLFF views by camera pose")
    parser.add_argument("--backend", required=True, help="DreamDB backend URL")
    parser.add_argument("--dataset-name", default="llff", help="Dataset name")
    parser.add_argument("--top-k", type=int, default=5, help="Number of nearest views")
    parser.add_argument(
        "--query-index",
        type=int,
        default=0,
        help="Use the pose at this index as the query (default: 0)",
    )
    args = parser.parse_args()

    ds = vd.Dataset.open_ref(args.dataset_name, backend=args.backend)
    print(f"Opened dataset '{args.dataset_name}' ({len(ds)} records)")

    # Grab the query pose from the dataset itself
    query_pose = None
    for batch in ds.iter_arrow_batches(batch_size=256, fields=["camera_pose"]):
        poses = batch.column("camera_pose").values.to_numpy(zero_copy_only=False)
        poses = poses.reshape(batch.num_rows, 12)
        if args.query_index < len(poses):
            query_pose = poses[args.query_index]
            break

    if query_pose is None:
        raise IndexError(f"Query index {args.query_index} out of range")

    print(f"\nQuery pose (index {args.query_index}):")
    print(f"  R = {query_pose[:9].reshape(3, 3).round(3)}")
    print(f"  t = {query_pose[9:12].round(3)}")

    # Vector search
    print(f"\nTop-{args.top_k} nearest camera poses:")
    print("-" * 60)

    batches = ds.iter_vector(
        field="camera_pose",
        query=query_pose.tolist(),
        top_k=args.top_k,
    )

    for batch in batches:
        anchors = batch["_time_anchors"]
        scene_ids = batch["scene_id"]
        view_indices = batch["view_index"]
        for anchor, scene, view in zip(anchors, scene_ids, view_indices):
            print(f"  anchor={anchor}  scene={scene}  view={view}")


if __name__ == "__main__":
    main()
