"""Immutable application tensor artifacts; no database access in local loading."""

from __future__ import annotations

import hashlib
import json
import shutil
import time

import numpy as np

PROFILE = "cartpole-four-frame-f32-v1"
KINDS = ("images", "sensors", "targets", "anchors")


def ready(batch):
    """Profile transform runs upstream, never in the local training loader."""
    images = batch["images"].transpose(0, 1, 4, 2, 3).reshape(-1, 12, 64, 64)
    return {
        "images": np.ascontiguousarray(images, dtype="<f4") * np.float32(1 / 255),
        "sensors": np.ascontiguousarray(batch["sensors"], dtype="<f4"),
        "targets": np.ascontiguousarray(batch["targets"], dtype="<f4"),
        "anchors": np.ascontiguousarray(batch["anchors"], dtype="<i8"),
    }


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def materialize(root, destination):
    from data import Reader

    start = time.perf_counter()
    receipt = json.loads((root / "receipt.json").read_text())
    reader = Reader((root / "backend").as_uri(), receipt)
    selection_seconds = time.perf_counter() - start
    destination.mkdir(exist_ok=False)
    manifest = {
        "profile": PROFILE,
        "source": receipt,
        "metadata": reader.metadata,
        "samples": reader.samples,
        "shards": [],
    }
    times = {
        "selection_seconds": selection_seconds,
        "read_decode_seconds": 0.0,
        "transform_seconds": 0.0,
        "write_hash_seconds": 0.0,
    }
    for first in range(0, len(reader.samples), 16):
        tick = time.perf_counter()
        batch, _ = reader.batch(reader.samples[first : first + 16])
        times["read_decode_seconds"] += time.perf_counter() - tick
        tick = time.perf_counter()
        arrays = ready(batch)
        times["transform_seconds"] += time.perf_counter() - tick
        tick = time.perf_counter()
        shard = {"first": first, "count": len(arrays["anchors"]), "files": {}}
        for name, array in arrays.items():
            filename = f"{first:06d}-{name}.npy"
            path = destination / filename
            with path.open("xb") as stream:
                np.save(stream, array, allow_pickle=False)
            shard["files"][name] = {
                "name": filename,
                "shape": list(array.shape),
                "dtype": array.dtype.str,
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        manifest["shards"].append(shard)
        times["write_hash_seconds"] += time.perf_counter() - tick
    with (destination / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, sort_keys=True)
    report = {
        **times,
        "total_seconds": time.perf_counter() - start,
        "source_backend_file_bytes": sum(
            p.stat().st_size for p in (root / "backend").rglob("*") if p.is_file()
        ),
        "artifact_file_bytes": sum(p.stat().st_size for p in destination.iterdir()),
        "samples": len(reader.samples),
        "source_manifest": reader.manifest,
        "profile": PROFILE,
        "boundary": "upstream materialization, not timed download",
    }
    print("MATERIALIZE " + json.dumps(report), flush=True)
    return report


def load_manifest(root):
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["profile"] == "cartpole-four-frame-f32-framebank-v1":
        from framebank import validate_manifest

        return validate_manifest(manifest)
    if manifest["profile"] != PROFILE:
        raise ValueError("unsupported training input profile")
    count = 0
    for shard in manifest["shards"]:
        if shard["first"] != count or not 1 <= shard["count"] <= 16:
            raise ValueError("invalid shard order/count")
        if set(shard["files"]) != set(KINDS):
            raise ValueError("missing tensor kind")
        for name, spec in shard["files"].items():
            if spec["name"] != f"{count:06d}-{name}.npy":
                raise ValueError("unexpected artifact path")
        count += shard["count"]
    if count != len(manifest["samples"]):
        raise ValueError("sample count mismatch")
    return manifest


def deliver(source, destination):
    """Local byte-only transport baseline; no decode or network speed claim."""
    start = time.perf_counter()
    manifest = load_manifest(source)
    destination.mkdir(exist_ok=False)
    count = size = 0
    groups = manifest["shards"] if "shards" in manifest else [{"files": manifest["files"]}]
    for shard in groups:
        for spec in shard["files"].values():
            checksum = hashlib.sha256()
            copied = 0
            with (
                (source / spec["name"]).open("rb") as src,
                (destination / spec["name"]).open("xb") as dst,
            ):
                while block := src.read(1024 * 1024):
                    dst.write(block)
                    checksum.update(block)
                    copied += len(block)
            if copied != spec["bytes"] or checksum.hexdigest() != spec["sha256"]:
                raise ValueError("delivery content mismatch; destination not ready")
            count += 1
            size += copied
    # No ready marker until all declared bytes have been copied and verified.
    with (
        (source / "manifest.json").open("rb") as src,
        (destination / "manifest.json").open("xb") as dst,
    ):
        shutil.copyfileobj(src, dst)
    report = {
        "files": count,
        "tensor_file_bytes": size,
        "copy_verify_seconds": time.perf_counter() - start,
        "boundary": "local file copy+hash; not remote download or crash-durable fsync",
    }
    print("DELIVERY " + json.dumps(report), flush=True)
    return report


class LocalBatches:
    """Read-only mmap files; no SDK/backend handle, PNG decoder or transform."""

    def __init__(self, root):
        start = time.perf_counter()
        self.manifest = load_manifest(root)
        self.samples = self.manifest["samples"]
        self.locations = []
        self.arrays = []
        dim = self.manifest["metadata"]["sensor_dim"]
        for shard in self.manifest["shards"]:
            mapped = {}
            shapes = {
                "images": (shard["count"], 12, 64, 64),
                "sensors": (shard["count"], 4, dim),
                "targets": (shard["count"], 1),
                "anchors": (shard["count"], 4),
            }
            for name, spec in shard["files"].items():
                path = root / spec["name"]
                array = np.load(path, mmap_mode="r", allow_pickle=False)
                dtype = np.dtype("<i8" if name == "anchors" else "<f4")
                if (
                    path.stat().st_size != spec["bytes"]
                    or array.shape != shapes[name]
                    or list(array.shape) != spec["shape"]
                    or array.dtype != dtype
                    or array.dtype.str != spec["dtype"]
                    or not array.flags.c_contiguous
                ):
                    raise ValueError("artifact does not match declared profile")
                mapped[name] = array
            index = len(self.arrays)
            self.arrays.append(mapped)
            self.locations.extend((index, row) for row in range(shard["count"]))
        self.open_seconds = time.perf_counter() - start
        self.sample_shapes = {name: array.shape[1:] for name, array in self.arrays[0].items()}

    def fill(self, indices, buffers):
        if not 1 <= len(indices) <= 16:
            raise ValueError("1..16 local sample indices required")
        for dest, index in enumerate(indices):
            if not 0 <= index < len(self.locations):
                raise ValueError("sample index outside artifact")
            shard, row = self.locations[index]
            for name, output in buffers.items():
                np.copyto(output[dest], self.arrays[shard][name][row], casting="no")

    def numpy_batch(self, indices):
        first = self.arrays[0]
        outputs = {
            name: np.empty((len(indices), *first[name].shape[1:]), dtype=first[name].dtype)
            for name in KINDS
        }
        self.fill(indices, outputs)
        return outputs
