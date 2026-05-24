"""Query the LanceDB table for views with similar camera poses.

Usage:
    python query.py --top-k 5
    python query.py --query-index 3 --top-k 5
"""

import argparse

import lancedb
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Query LLFF views by camera pose (LanceDB)")
    parser.add_argument("--db-path", default="./lancedb_data", help="LanceDB directory")
    parser.add_argument("--table-name", default="llff_poses", help="Table name")
    parser.add_argument("--top-k", type=int, default=5, help="Number of nearest views")
    parser.add_argument("--query-index", type=int, default=0, help="Use pose at this index as query")
    args = parser.parse_args()

    db = lancedb.connect(args.db_path)
    table = db.open_table(args.table_name)
    print(f"Opened table '{args.table_name}' ({table.count_rows()} rows)")

    # Get the query pose
    df = table.to_pandas()
    query_pose = np.array(df.iloc[args.query_index]["camera_pose"], dtype=np.float32)

    print(f"\nQuery pose (index {args.query_index}):")
    print(f"  R = {query_pose[:9].reshape(3, 3).round(3)}")
    print(f"  t = {query_pose[9:12].round(3)}")

    # Vector search
    results = (
        table.search(query_pose.tolist())
        .metric("cosine")
        .limit(args.top_k)
        .select(["scene_id", "view_index", "image_path"])
        .to_pandas()
    )

    print(f"\nTop-{args.top_k} nearest camera poses:")
    print("-" * 60)
    for _, row in results.iterrows():
        print(
            f"  scene={row['scene_id']}  view={row['view_index']}  "
            f"dist={row.get('_distance', 'n/a'):.4f}  "
            f"image={row['image_path']}"
        )


if __name__ == "__main__":
    main()
