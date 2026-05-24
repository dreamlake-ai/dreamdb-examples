"""Query the LanceDB table for views with similar camera poses.

Usage:
    python query.py --top-k 5
    python query.py --query-index 3 --top-k 5
"""

import lancedb
import numpy as np
from params_proto import proto


@proto.cli
def main(
    db_path: str = "./lancedb_data",  # LanceDB directory
    table_name: str = "llff_poses",  # Table name
    top_k: int = 5,  # Number of nearest views
    query_index: int = 0,  # Use the pose at this index as the query
):
    """Query LLFF views by camera pose (LanceDB)."""
    db = lancedb.connect(db_path)
    table = db.open_table(table_name)
    print(f"Opened table '{table_name}' ({table.count_rows()} rows)")

    df = table.to_pandas()
    query_pose = np.array(df.iloc[query_index]["camera_pose"], dtype=np.float32)

    print(f"\nQuery pose (index {query_index}):")
    print(f"  R = {query_pose[:9].reshape(3, 3).round(3)}")
    print(f"  t = {query_pose[9:12].round(3)}")

    results = (
        table.search(query_pose.tolist())
        .metric("cosine")
        .limit(top_k)
        .select(["scene_id", "view_index", "image_path"])
        .to_pandas()
    )

    print(f"\nTop-{top_k} nearest camera poses:")
    print("-" * 60)
    for _, row in results.iterrows():
        print(
            f"  scene={row['scene_id']}  view={row['view_index']}  "
            f"dist={row.get('_distance', 'n/a'):.4f}  "
            f"image={row['image_path']}"
        )


if __name__ == "__main__":
    main()
