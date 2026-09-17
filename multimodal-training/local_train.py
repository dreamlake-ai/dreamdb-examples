"""Train only from delivered tensors; no DreamDB, backend or decoder imports."""

from __future__ import annotations

import json
import resource
import time

import numpy as np
from network import make_model
from stages import LocalBatches, ready


def check_inputs(store, root):
    # Witness data is acceptance-only and never becomes optimizer input.
    with np.load(root / "witness.npz", allow_pickle=False) as witness:
        for first in range(0, len(store.samples), 16):
            indices = list(range(first, min(first + 16, len(store.samples))))
            actual = store.numpy_batch(indices)
            anchors = actual["anchors"]
            rows = anchors - 1
            expected = ready(
                {
                    "anchors": anchors,
                    "images": witness["images"][rows],
                    "sensors": witness["sensors"][rows],
                    "targets": witness["actions"][rows[:, -1]],
                }
            )
            for name in actual:
                a, b = actual[name], expected[name]
                assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), (
                    name
                )
            for row, index in zip(rows, indices, strict=True):
                key, start = store.samples[index]
                np.testing.assert_array_equal(
                    witness["identities"][row], [[*key, step] for step in range(start, start + 4)]
                )


def train_local(root, *, verify=False, layout="windows"):
    setup_started = time.perf_counter()
    import torch
    from torch import nn

    torch.manual_seed(71)
    torch.set_num_threads(4)
    if layout == "windows":
        store = LocalBatches(root / "delivered")
    elif layout == "frames":
        from framebank import FrameBatches

        store = FrameBatches(root / "delivered-frames")
    else:
        raise ValueError("unknown training-ready layout")
    check_started = time.perf_counter()
    if verify:
        check_inputs(store, root)
        assert not (root / "backend").exists(), (
            "acceptance requires original source path unavailable"
        )
    check_seconds = time.perf_counter() - check_started if verify else 0.0
    training = [i for i, (key, _) in enumerate(store.samples) if key[0] < 6]
    validation = [i for i, (key, _) in enumerate(store.samples) if key[0] >= 6]
    assert training and validation
    assert not (
        {tuple(store.samples[i][0]) for i in training}
        & {tuple(store.samples[i][0]) for i in validation}
    )
    shapes = {name: shape for name, shape in store.sample_shapes.items() if name != "anchors"}
    # Reuse a single pinned batch and one device batch. Compute completes before
    # either is reused; no async-buffer lifetime promise based on timing luck.
    host = {
        name: torch.empty((16, *shape), dtype=torch.float32, pin_memory=True)
        for name, shape in shapes.items()
    }
    host_numpy = {name: tensor.numpy() for name, tensor in host.items()}
    device = {name: torch.empty_like(tensor, device="cuda:0") for name, tensor in host.items()}
    start_event, ready_event = (
        torch.cuda.Event(enable_timing=True),
        torch.cuda.Event(enable_timing=True),
    )

    def transfer(n):
        tick = time.perf_counter()
        start_event.record()
        for name in device:
            device[name][:n].copy_(host[name][:n], non_blocking=True)
        ready_event.record()
        ready_event.synchronize()
        return time.perf_counter() - tick, start_event.elapsed_time(ready_event) / 1000

    model = make_model(store.manifest["metadata"]["sensor_dim"]).cuda()
    initial = [p.detach().clone() for p in model.parameters()]
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    setup_seconds = time.perf_counter() - setup_started - check_seconds
    rng = np.random.default_rng(71)
    totals = {
        "host_gather_seconds": 0.0,
        "h2d_ready_wall_seconds": 0.0,
        "h2d_event_seconds": 0.0,
        "compute_seconds": 0.0,
        "batch_bytes": 0,
    }
    first_batch = None
    losses = []
    transfer_checked = False
    for _ in range(2):
        order = rng.permutation(training)
        for offset in range(0, len(order), 16):
            indices = order[offset : offset + 16]
            tick = time.perf_counter()
            store.fill(indices, host_numpy)
            gather = time.perf_counter() - tick
            wall, event = transfer(len(indices))
            totals["host_gather_seconds"] += gather
            totals["h2d_ready_wall_seconds"] += wall
            totals["h2d_event_seconds"] += event
            totals["batch_bytes"] += sum(
                t[: len(indices)].numel() * t.element_size() for t in host.values()
            )
            if first_batch is None:
                first_batch = {"gather_seconds": gather, "h2d_ready_wall_seconds": wall}
            if not transfer_checked:
                for name in host:
                    assert torch.equal(
                        device[name][: len(indices)].cpu(), host[name][: len(indices)]
                    ), name
                transfer_checked = True
            tick = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            prediction = model(device["images"][: len(indices)], device["sensors"][: len(indices)])
            loss = nn.functional.mse_loss(prediction, device["targets"][: len(indices)])
            assert torch.isfinite(loss)
            loss.backward()
            optimizer.step()
            torch.cuda.synchronize()
            totals["compute_seconds"] += time.perf_counter() - tick
            losses.append(float(loss.detach()))
    assert all(torch.isfinite(p).all() for p in model.parameters())
    assert any(not torch.equal(a, p) for a, p in zip(initial, model.parameters(), strict=True))
    model.eval()
    squared_error = count = 0
    with torch.inference_mode():
        for offset in range(0, len(validation), 16):
            indices = validation[offset : offset + 16]
            store.fill(indices, host_numpy)
            transfer(len(indices))
            error = (
                model(device["images"][: len(indices)], device["sensors"][: len(indices)])
                - device["targets"][: len(indices)]
            ).square()
            assert torch.isfinite(error).all()
            squared_error += float(error.sum())
            count += error.numel()

    # One direct copy reference for the same ready batch, not a device simulator
    # or theoretical DRAM/PCIe rating. No file IO/decode/transform in this baseline.
    reference = store.numpy_batch(list(range(16)))
    floor = []
    for _ in range(3):
        tick = time.perf_counter()
        for name in host:
            np.copyto(host_numpy[name], reference[name], casting="no")
        gather = time.perf_counter() - tick
        wall, event = transfer(16)
        floor.append(
            {
                "host_copy_seconds": gather,
                "h2d_ready_wall_seconds": wall,
                "h2d_event_seconds": event,
            }
        )
    report = {
        "result": "PASS",
        "source_manifest": store.manifest["source"]["manifest"],
        "profile": store.manifest["profile"],
        "map_open_seconds": store.open_seconds,
        "setup_including_torch_cuda_model_seconds": setup_seconds,
        "acceptance_check_seconds": check_seconds,
        "exact_ready_inputs": True if verify else None,
        "completed_device_copy_exact": transfer_checked,
        "source_path_unavailable": not (root / "backend").exists(),
        "train_samples": len(training),
        "validation_samples": len(validation),
        "optimizer_updates": len(losses),
        "train_first_loss": losses[0],
        "train_last_loss": losses[-1],
        "validation_mse": squared_error / count,
        "training": totals,
        "first_training_batch": first_batch,
        "warm_contiguous_copy_reference": floor,
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "boundary": "acceptance warms file pages; no decode/normalize/layout conversion; gather+completed H2D, not theoretical limits",
    }
    print("LOCAL_TRAIN_ACCEPTANCE " + json.dumps(report), flush=True)
