"""Small synchronous storage primitive; the future capture writer owns this object.

Only public DreamDB APIs. This milestone does not implement asynchronous capture,
backpressure or mjlab hooks. One new local backend per run prevents overwriting
an existing dataset; this is NOT a remote create-only publication implementation.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import dreamdb
import numpy as np

FORMAT = "mjlab-reference-v1"
I64_MAX = (1 << 63) - 1
IDENTITY = ["kind", "env_id", "episode_id", "step_id", "sim_step"]
FLAGS = ["terminated", "truncated", "next_observation_valid"]
STATE = ["qpos", "qvel", "sim_time"]
EVENT_FIELDS = IDENTITY + FLAGS + STATE + ["obs_t", "action", "reward", "obs_after"]
MOCAP_FIELDS = ["mocap_pos", "mocap_quat"]


def event_fields(metadata):
    return EVENT_FIELDS + [name for name in MOCAP_FIELDS if name in metadata["dimensions"]]


def schema(metadata: dict, model_size: int) -> dreamdb.Schema:
    result = dreamdb.Schema()
    result.add_scalar_categorical("kind", required=True)
    for name in IDENTITY[1:]:
        result.add_scalar_int(name, required=False)
    for name in FLAGS:
        result.add_scalar_bool(name, required=False)
    for name in ["reward", "sim_time"]:
        result.add_scalar_float(name, required=False)
    result.add_scalar_string("metadata", required=False)
    for name, dim in metadata["dimensions"].items():
        result.add_array(name, "f32", [dim], required=False)
    result.add_array("model_bytes", "u8", [model_size], required=False)
    return result


class LocalRunWriter:
    """Own one synchronous run; append acknowledges publication, not enqueueing."""

    def __init__(self, root: Path, metadata: dict, model: bytes):
        dimensions = metadata["dimensions"]
        base = {"qpos", "qvel", "obs_t", "action", "obs_after"}
        if not base <= dimensions.keys() or set(dimensions) - base - set(MOCAP_FIELDS):
            raise ValueError("declare the five fixed-shape state/transition arrays")
        if bool("mocap_pos" in dimensions) != bool("mocap_quat" in dimensions):
            raise ValueError("mocap position and quaternion must be declared together")
        if not model or any(type(n) is not int or n <= 0 for n in dimensions.values()):
            raise ValueError("model and array dimensions must be nonempty")
        self.metadata = {
            **metadata,
            "format": FORMAT,
            "anchor_encoding": "logical-record-ordinal-v1",
            "dreamdb_version": importlib.metadata.version("dreamdb"),
            "model_size": len(model),
            "model_sha256": hashlib.sha256(model).hexdigest(),
        }
        self.root = root.resolve()
        self.root.mkdir(parents=False, exist_ok=False)
        self.backend = self.root.as_uri()
        self.dataset = dreamdb.Dataset.create(
            "run", schema(self.metadata, len(model)), backend=self.backend
        )
        self._next = 0
        self._events = 0
        self._failed = False
        self._finished = False
        self._publish(
            [
                {
                    "kind": "run_start",
                    "metadata": json.dumps(self.metadata, sort_keys=True, allow_nan=False),
                    "model_bytes": np.frombuffer(model, dtype=np.uint8),
                }
            ]
        )

    def _publish(self, rows: list[dict]) -> str:
        if self._failed or self._finished:
            raise RuntimeError("writer failed or has already finished")
        if self._next + len(rows) >= I64_MAX:
            raise OverflowError("logical anchors exceed signed read-window range")
        samples = [dict(row, _anchor=self._next + i) for i, row in enumerate(rows)]
        try:
            count = self.dataset.append_many(samples, commit=True)
            if count != len(samples):
                raise RuntimeError(f"append acknowledged {count}/{len(samples)} rows")
            tip = self.dataset.current_manifest()
            if not tip:
                raise RuntimeError("publication returned no Manifest")
        except BaseException:
            # No automatic retry of an ambiguous publication.
            self._failed = True
            raise
        self._next += len(samples)
        return tip

    def append(self, events: list[dict]) -> str:
        if not events:
            raise ValueError("empty batch")
        for row in events:
            if row.get("kind") not in {"reset", "transition"}:
                raise ValueError("only reset/transition events may be appended")
            if set(row) - set(event_fields(self.metadata)):
                raise ValueError("unknown event fields or caller-supplied anchor")
            for name in IDENTITY[1:]:
                if type(row.get(name)) is not int or row[name] < 0:
                    raise ValueError(f"invalid {name}")
            needed = {"qpos", "qvel", "obs_after"}
            if row["kind"] == "transition":
                if any(type(row.get(name)) is not bool for name in FLAGS):
                    raise ValueError("transition requires explicit boolean flags")
                if "reward" not in row:
                    raise ValueError("transition requires reward")
                needed = {"qpos", "qvel", "obs_t", "action"}
                if row["next_observation_valid"]:
                    needed.add("obs_after")
                elif "obs_after" in row:
                    raise ValueError("invalid next observation must be absent")
            needed.update(name for name in MOCAP_FIELDS if name in self.metadata["dimensions"])
            if not needed <= row.keys() or "sim_time" not in row:
                raise ValueError("missing state/observation components")
            for name, dim in self.metadata["dimensions"].items():
                if name in row:
                    value = row[name]
                    if not isinstance(value, np.ndarray) or value.dtype != np.dtype("<f4"):
                        raise ValueError(f"{name}: explicit little-endian float32 required")
                    if value.shape != (dim,) or not np.isfinite(value).all():
                        raise ValueError(f"{name}: wrong shape or nonfinite state")
        tip = self._publish(events)
        self._events += len(events)
        return tip

    def finish(self) -> str:
        """Clean capture end, not a claim that every episode terminated."""
        tip = self._publish(
            [
                {
                    "kind": "run_end",
                    "metadata": json.dumps({"event_rows": self._events}),
                }
            ]
        )
        self._finished = True
        return tip


def read_window(dataset, fields: list[str], start: int, end: int) -> list[dict]:
    """Materialize only a caller-bounded window with explicit projection."""
    rows = []
    for batch in dataset.iter_all_batches(
        fields=fields, start_ns=start, end_ns=end, batch_size=128
    ):
        for i, anchor in enumerate(batch["_time_anchors"]):
            row = {"_anchor": anchor}
            row.update(
                {
                    name: values[i]
                    for name, values in batch.items()
                    if name != "_time_anchors" and values[i] is not None
                }
            )
            rows.append(row)
    return sorted(rows, key=lambda row: row["_anchor"])


def read_header(dataset) -> tuple[dict, bytes]:
    rows = read_window(dataset, ["kind", "metadata", "model_bytes"], 0, 1)
    if len(rows) != 1 or rows[0]["kind"] != "run_start":
        raise ValueError("missing run header")
    metadata = json.loads(rows[0]["metadata"])
    if metadata["format"] != FORMAT:
        raise ValueError("unsupported recording format")
    model = rows[0]["model_bytes"].tobytes()
    if len(model) != metadata["model_size"]:
        raise ValueError("model length mismatch")
    if hashlib.sha256(model).hexdigest() != metadata["model_sha256"]:
        raise ValueError("model digest mismatch")
    return metadata, model


def read_episode(dataset, env_id: int, episode_id: int, fields=None) -> list[dict]:
    """Public scalar lookup + projected, bounded windows; not a streaming index.

    Anchor lists are materialized by query_scalar. Memory therefore grows with
    matching env/episode anchors. This is a measured prototype limitation.
    """
    anchors = set(dataset.query_scalar("env_id", "==", env_id))
    anchors.intersection_update(dataset.query_scalar("episode_id", "==", episode_id))
    if fields is None:
        header = read_window(dataset, ["metadata"], 0, 1)
        fields = event_fields(json.loads(header[0]["metadata"]))
    rows = []
    # Fetch each fixed logical window once, not once per selected anchor.
    for window in sorted({anchor // 256 for anchor in anchors}):
        rows.extend(
            row
            for row in read_window(dataset, fields, window * 256, (window + 1) * 256)
            if row["_anchor"] in anchors
        )
    if {row["_anchor"] for row in rows} != anchors:
        raise ValueError("projected read did not return every selected event")
    return rows


def episode_status(rows: list[dict]) -> str:
    """Complete requires reset + contiguous transitions + final terminal flags."""
    if not rows or rows[0]["kind"] != "reset":
        return "incomplete"
    identities = {(row["env_id"], row["episode_id"]) for row in rows}
    if len(identities) != 1:
        raise ValueError("mixed episode identities")
    transitions = rows[1:]
    if any(row["kind"] != "transition" or row["step_id"] != i for i, row in enumerate(transitions)):
        return "incomplete"
    if any(row["terminated"] or row["truncated"] for row in transitions[:-1]):
        raise ValueError("transition after terminal state within one episode")
    if transitions and (transitions[-1]["terminated"] or transitions[-1]["truncated"]):
        return "complete"
    return "incomplete"
