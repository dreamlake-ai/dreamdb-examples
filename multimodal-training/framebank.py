"""Lossless frame-bank representation of the fixed float32 window profile."""

from __future__ import annotations

import json
import time

import numpy as np
from stages import LocalBatches, digest, load_manifest

PROFILE = "cartpole-four-frame-f32-framebank-v1"
FILES = ("images", "sensors", "anchors", "windows", "targets")


def validate_manifest(manifest):
    if manifest["profile"] != PROFILE or set(manifest["files"]) != set(FILES):
        raise ValueError("unsupported frame-bank layout")
    if not 1 <= manifest["frames"] <= 4096 or not manifest["samples"]:
        raise ValueError("frame-bank size outside reference bounds")
    for name, spec in manifest["files"].items():
        if spec["name"] != f"frames-{name}.npy":
            raise ValueError("unexpected frame-bank filename")
    return manifest


def repack(source, destination):
    tick = time.perf_counter()
    old = LocalBatches(source)
    # Keep references into mapped files, not a second heap copy of all windows.
    references = {}
    identity_anchor = {}
    for sample, (key, start) in enumerate(old.samples):
        shard, row = old.locations[sample]
        for frame, anchor in enumerate(old.arrays[shard]["anchors"][row]):
            anchor = int(anchor)
            identity = (*key, start + frame)
            if identity in identity_anchor and identity_anchor[identity] != anchor:
                raise ValueError("one frame identity has multiple anchors")
            if anchor in references and references[anchor][0] != identity:
                raise ValueError("one anchor has multiple frame identities")
            identity_anchor[identity] = anchor
            references.setdefault(anchor, (identity, shard, row, frame))
    anchors = sorted(references, key=lambda a: references[a][0])
    if len(anchors) > 4096:
        raise ValueError("frame-bank exceeds bounded reference scope")
    slots = {anchor: i for i, anchor in enumerate(anchors)}
    dim = old.manifest["metadata"]["sensor_dim"]
    shapes = {
        "images": (len(anchors), 3, 64, 64),
        "sensors": (len(anchors), dim),
        "anchors": (len(anchors),),
        "windows": (len(old.samples), 4),
        "targets": (len(old.samples), 1),
    }
    destination.mkdir(exist_ok=False)
    mapped = {}
    for name, shape in shapes.items():
        dtype = "<i8" if name in ("anchors", "windows") else "<f4"
        mapped[name] = np.lib.format.open_memmap(
            destination / f"frames-{name}.npy", mode="w+", dtype=dtype, shape=shape
        )
    for slot, anchor in enumerate(anchors):
        _, shard, row, frame = references[anchor]
        mapped["images"][slot] = old.arrays[shard]["images"][row].reshape(4, 3, 64, 64)[frame]
        mapped["sensors"][slot] = old.arrays[shard]["sensors"][row, frame]
        mapped["anchors"][slot] = anchor
    for sample, (shard, row) in enumerate(old.locations):
        indices = [slots[int(a)] for a in old.arrays[shard]["anchors"][row]]
        if indices != list(range(indices[0], indices[0] + 4)):
            raise ValueError("window is not a contiguous episode slice")
        mapped["windows"][sample] = indices
        mapped["targets"][sample] = old.arrays[shard]["targets"][row]
    manifest = {
        "profile": PROFILE,
        "source": old.manifest["source"],
        "metadata": old.manifest["metadata"],
        "samples": old.samples,
        "frames": len(anchors),
        "repacked_from_profile": old.manifest["profile"],
        "files": {},
    }
    for name, array in mapped.items():
        array.flush()
        path = destination / f"frames-{name}.npy"
        manifest["files"][name] = {
            "name": path.name,
            "shape": list(array.shape),
            "dtype": array.dtype.str,
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
    with (destination / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, sort_keys=True)
    report = {
        "repack_seconds": time.perf_counter() - tick,
        "unique_frames": len(anchors),
        "window_frame_slots": 4 * len(old.samples),
        "samples": len(old.samples),
        "original_artifact_bytes": sum(p.stat().st_size for p in source.iterdir()),
        "framebank_artifact_bytes": sum(p.stat().st_size for p in destination.iterdir()),
        "boundary": "repack after original materialization; not direct database-to-bank",
    }
    print("FRAMEBANK_REPACK " + json.dumps(report), flush=True)
    # Primary public result: every output window must still be the same tensor.
    new = FrameBatches(destination)
    for first in range(0, len(old.samples), 16):
        selected = list(range(first, min(first + 16, len(old.samples))))
        before, after = old.numpy_batch(selected), new.numpy_batch(selected)
        for name in before:
            a, b = before[name], after[name]
            if a.dtype != b.dtype or a.shape != b.shape or a.tobytes() != b.tobytes():
                raise ValueError(f"repack changed output {name}")
    print(f"FRAMEBANK_EXACT {len(old.samples)} windows compared", flush=True)
    return report


class FrameBatches:
    def __init__(self, root):
        tick = time.perf_counter()
        self.manifest = load_manifest(root)
        validate_manifest(self.manifest)
        self.samples = self.manifest["samples"]
        frames, count = self.manifest["frames"], len(self.samples)
        dim = self.manifest["metadata"]["sensor_dim"]
        shapes = {
            "images": (frames, 3, 64, 64),
            "sensors": (frames, dim),
            "anchors": (frames,),
            "windows": (count, 4),
            "targets": (count, 1),
        }
        self.bank = {}
        for name, spec in self.manifest["files"].items():
            path = root / spec["name"]
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            dtype = np.dtype("<i8" if name in ("anchors", "windows") else "<f4")
            if (
                path.stat().st_size != spec["bytes"]
                or array.shape != shapes[name]
                or list(array.shape) != spec["shape"]
                or array.dtype != dtype
                or array.dtype.str != spec["dtype"]
                or not array.flags.c_contiguous
            ):
                raise ValueError("frame-bank tensor shape/dtype mismatch")
            self.bank[name] = array
        windows = self.bank["windows"]
        if (
            np.any(windows[:, 0] < 0)
            or np.any(windows[:, -1] >= frames)
            or not np.all(np.diff(windows, axis=1) == 1)
        ):
            raise ValueError("invalid contiguous frame window")
        self.sample_shapes = {
            "images": (12, 64, 64),
            "sensors": (4, dim),
            "targets": (1,),
            "anchors": (4,),
        }
        self.open_seconds = time.perf_counter() - tick

    def fill(self, indices, buffers):
        if not 1 <= len(indices) <= 16:
            raise ValueError("1..16 local sample indices required")
        for dest, index in enumerate(indices):
            if not 0 <= index < len(self.samples):
                raise ValueError("sample index outside frame bank")
            first = int(self.bank["windows"][index, 0])
            for name, output in buffers.items():
                if name == "targets":
                    value = self.bank[name][index]
                else:
                    value = self.bank[name][first : first + 4]
                    if name == "images":
                        value = value.reshape(12, 64, 64)  # Contiguous view; no transform/copy.
                np.copyto(output[dest], value, casting="no")

    def numpy_batch(self, indices):
        outputs = {
            name: np.empty((len(indices), *shape), dtype="<i8" if name == "anchors" else "<f4")
            for name, shape in self.sample_shapes.items()
        }
        self.fill(indices, outputs)
        return outputs
