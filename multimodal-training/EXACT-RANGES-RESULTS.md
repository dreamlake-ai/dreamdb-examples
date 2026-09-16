# Exact training range results — 2026-09-16

Issue #20; executed source `a868e54` (subsequent changes only record results).
Slurm **147496**, `bos14-node-085`, COMPLETED / exit 0, elapsed **3m45s**.
One real mjlab capture, 8 environments × 4 episodes × 32 steps = 1,024 rows;
capture 19.9721 s. Ephemeral snapshot:
`d34okvjvc7drysyfsbtj7byvkdtjaxwc2i76gbym4fu3lpdbo2dl4`.

Runtime: DreamDB 0.0.13, mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1,
NumPy 2.5.3, Pillow 12.3.0; shared runtime left unchanged. One RTX PRO 6000,
four application threads, requested 4 CPUs / 16 GiB (Slurm allocated 32 CPUs).
No unmerged core optimization or application cache was used in either mode.

## Result

Same dataset, seed, model, 696 training windows, two epochs, 88 updates per run.
Every batch passed the existing independent witness comparison of anchor
identity/order, transformed pixels, sensors and actions. This is a complete
input comparison for this fixture, not a general SDK correctness claim.

| Measurement | Fixed pages 1 | Exact 1 | Exact 2 | Fixed pages 2 |
|---|---:|---:|---:|---:|
| Training loop (s) | 54.2664 | 31.5333 | 31.3848 | 52.5123 |
| Input wait (s) | 53.7712 | 31.0899 | 30.9366 | 52.0537 |
| SDK time in producer (s) | 52.5759 | 29.9487 | 29.8329 | 50.8844 |
| SDK calls | 1,614 | 5,008 | 5,008 | 1,614 |
| Returned rows | 51,609 | 5,392 | 5,392 | 51,609 |
| Returned payload bytes | 129,675,661 | 13,585,025 | 13,585,025 | 129,675,661 |
| Selected rows | 5,392 | 5,392 | 5,392 | 5,392 |
| Selected payload bytes | 13,585,025 | 13,585,025 | 13,585,025 | 13,585,025 |
| PNG decode (s) | 0.4302 | 0.4183 | 0.4170 | 0.4361 |
| GPU compute (s) | 0.3258 | 0.2805 | 0.2887 | 0.2953 |
| Transfer (s) | 0.0294 | 0.0275 | 0.0269 | 0.0300 |
| Witness comparison (s) | 0.1188 | 0.1145 | 0.1129 | 0.1139 |
| First batch (s) | 2.5746 | 1.4426 | 1.4011 | 1.9297 |
| Worker max RSS (KiB) | 760,708 | 760,080 | 760,904 | 760,572 |
| Parent max RSS (KiB) | 1,469,384 | 1,447,524 | 1,447,132 | 1,449,952 |

Selected rows are unique within a batch, recounted across batches/epochs.
All four runs decoded exactly 5,392 selected frames. Payload counters include
encoded PNG bytes and sensor/action array bytes, not Track metadata or
filesystem/network I/O. Identity scans are excluded from those counters, but
their cost is included in startup and first-batch time. RSS values are process
high-water marks, not a sum of unique physical memory.

Exact ranges reduce returned payload **89.52%**, from approximately **9.55x**
selected bytes to **1.00x**. Calls increase **3.10x**. Paired loop speedups are
**1.72x** and **1.67x** (approximately 40% less time), despite more calls.
Four runs on one node are not a confidence interval or a cold-cache benchmark;
OS caches were not reset. There is no claim about datasets larger than RAM,
S3 throughput, GPU saturation or a theoretical limit.

## What remains

Input waiting still occupies roughly 99% of the exact-mode loop. Its producer
spends about 30 seconds inside 5,008 public SDK calls, while PNG decode takes
about 0.42 seconds. Removing unwanted payload helps substantially, but does
not remove per-call metadata, dispatch and conversion work. This measurement
does not separate those costs and does not prove the benefit of a particular
new API. Native small-Track reuse (core#386) and array overlap (core#384) were
not included; their combined training effect remains unmeasured.

Keep the existing default policy unchanged. `exact` is an explicit reference
mode, not a universally optimal planner. The next useful comparison can apply
the core improvements to this same exact-read workload before deciding whether
a projected multi-anchor API is warranted. No additional cache or prepared
training artifact is needed to obtain the measured benefit here.

## Reproduction and cleanup

From this source, copy `multimodal-training/` to an isolated cluster task's
`source/`, install `dreamdb==0.0.13 --no-deps` into its private `sdk/`, and submit
`sbatch source/exact-ranges.slurm` from the task root. The script captures once
and runs `ondemand.py prefetch/exact/exact/prefetch` in that order using the
existing shared runtime. No worker SSH or shared-runtime changes are needed.
Native syntax preflight used `ast.parse`; the shell script passed `bash -n`.

The capture, witnesses, private SDK, logs and task cache are disposable and
removed after this record is committed and pushed. Reproduction generates a
new content-addressed snapshot; the ephemeral hash above is an observation,
not a promise that the original local backend remains available. No raw
training data or large evidence archive is committed.
