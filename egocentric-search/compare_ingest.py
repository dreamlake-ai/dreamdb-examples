"""Compare the two completed real runs; no backend requests or writes."""
import argparse
import json
from pathlib import Path
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("baseline", type=Path)
ap.add_argument("candidate", type=Path)
ap.add_argument("--out", type=Path, required=True)
a = ap.parse_args()
base = json.loads((a.baseline / "pilot-result.json").read_text())
new = json.loads((a.candidate / "pilot-result.json").read_text())
if new.get("status") != "PASS":
    raise SystemExit("candidate verification is incomplete")
assert base["source_revision"] == new["source_revision"]
assert base["model_revision"] == new["model_revision"]
assert base["ingest"] == new["ingest"]
assert base["readback_media_bytes"] == new["readback_media_bytes"]
left = sorted((a.baseline / "vecs").rglob("*.npz"))
right = sorted((a.candidate / "vecs").rglob("*.npz"))
assert [p.relative_to(a.baseline / "vecs") for p in left] == [p.relative_to(a.candidate / "vecs") for p in right]
count = 0
for x, y in zip(left, right):
    with np.load(x, allow_pickle=False) as xb, np.load(y, allow_pickle=False) as yb:
        for key in ("frame_siglip__anchors", "frame_siglip__vecs"):
            assert xb[key].shape == yb[key].shape and xb[key].dtype == yb[key].dtype
            assert xb[key].tobytes() == yb[key].tobytes(), (x.name, key)
        count += len(xb["frame_siglip__anchors"])
assert count == base["ingest"]["frames"]
old_s = base["stages_s"]["acquire_decode_encode_ingest"]
new_s = new["stages_s"]["acquire_decode_encode_ingest"]
result = {"status": "PASS", "same_vector_and_anchor_records": count,
          "baseline_ingest_s": old_s, "optimized_ingest_s": new_s,
          "speed_ratio": old_s / new_s,
          "baseline_phases": base["ingest_stage_seconds"],
          "optimized_phases": new["ingest_stage_seconds"],
          "limits": "one observed pair, no controlled network/cache equivalence"}
a.out.write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
