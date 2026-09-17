"""Fixed public ranges, projection-specific time; no storage internals."""
import json
import time
from pathlib import Path
import sys

from data import Reader, Stats


root = Path(sys.argv[1]).resolve()
reader = Reader((root / "backend").as_uri(), json.loads((root / "receipt.json").read_text()))
fields = {"image": ["image"], "arrays": ["sensor", "action"],
          "combined": ["image", "sensor", "action"]}
result = {key: {"sdk_seconds": 0., "collect_seconds": 0., "rows": 0, "bytes": 0}
          for key in fields}
for page in range(1, 9):
    names = list(fields) if page % 2 else list(reversed(fields))
    for name in names:
        stats = Stats()
        started = time.perf_counter()
        rows = reader._read(fields[name], 1 + (page - 1) * 32, 1 + page * 32, stats)
        elapsed = time.perf_counter() - started
        assert len(rows) == 32
        result[name]["sdk_seconds"] += stats.sdk_seconds
        result[name]["collect_seconds"] += elapsed - stats.sdk_seconds
        result[name]["rows"] += len(rows)
        result[name]["bytes"] += stats.payload_bytes
print("READ_PROBE " + json.dumps(result), flush=True)
