# Combined native reads: real training result (2026-09-17)

Issue #22. Application scripts executed from `f8f0191`; later changes only
record results and clarify the private build-tool installation. Core pins are
in `COMBINED-CORE.md`; combined commit is available on core's benchmark branch
`bench/combined-training-reads`. Neither core PR was merged or released here.

## Build and execution identity

Both wheels were built on Slurm node `bos14-node-031` with Rust/cargo 1.98.1,
maturin 1.9.6, Python 3.12.3, unchanged release settings (fat LTO, one codegen
unit, opt-level 3, overflow checks), four cargo jobs and a task-local target
directory. Both have nominal version 0.0.13; that string is not their identity.

| Variant | Core commit | Wheel SHA-256 |
|---|---|---|
| Baseline | `c6b31ab307eaf4f2e8b56e0c71d8af9163142438` | `bbbeaecc4116e2cb92ffba68d5a7eba89d44280cdd71f4876c41c001a4381ca7` |
| Combined | `aa4efd18c63e2e644d3bf81f7f5f119f850e956e` | `d420e7ef7c631e66330de8b1966aa30037da4b2a817c453acad045ee3823b126` |

Successful build job **147603**, COMPLETED / exit 0, 2m44s. Build+install
intervals were baseline 81 s and combined 83 s; cargo reported 78 s and 79 s.
These are not build-performance comparisons: the task cache was shared and
baseline had already compiled during an earlier failed install attempt.

Training job **147604**, same node, COMPLETED / exit 0, **2m09s**. One RTX PRO
6000, requested 4 CPUs / 16 GiB; scheduler allocated 32 CPUs, application thread
count remained four. Each run printed the native module path from its own
`sdk-baseline` or `sdk-combined` private directory. Shared runtime unchanged:
mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1, NumPy 2.5.3, Pillow 12.3.0.

Capture: 8 environments × 4 episodes × 32 steps = 1,024 rows, 19.5037 s,
using baseline. One ephemeral snapshot for all four runs:
`d2zvtjjemsxgkmk3m25kpnslmykogjygbgf4hdsab2xpickqpshdw`.

## Direct application check and measurements

Exact ranges in all runs, no application cache, two-batch queue. Every run
completed 88 updates across two epochs. Every batch's anchor identities/order,
transformed pixels, sensors and actions matched the independent capture
witnesses. No extra validation framework or new CI run was used.

| Measurement | Baseline 1 | Combined 1 | Combined 2 | Baseline 2 |
|---|---:|---:|---:|---:|
| Training loop (s) | 32.8982 | 5.5096 | 5.1325 | 30.9320 |
| Input wait (s) | 31.6956 | 5.0822 | 4.6605 | 30.4326 |
| Producer SDK time (s) | 31.2580 | 3.8019 | 3.4727 | 29.3564 |
| SDK calls | 5,008 | 5,008 | 5,008 | 5,008 |
| Returned / selected rows | 5,392 / 5,392 | 5,392 / 5,392 | 5,392 / 5,392 | 5,392 / 5,392 |
| Returned / selected bytes | 13,585,025 / 13,585,025 | 13,585,025 / 13,585,025 | 13,585,025 / 13,585,025 | 13,585,025 / 13,585,025 |
| PNG decode (s) | 0.4128 | 0.4688 | 0.4546 | 0.4141 |
| GPU compute (s) | 1.0121 | 0.2730 | 0.2652 | 0.2807 |
| Transfer (s) | 0.0276 | 0.0240 | 0.0230 | 0.0267 |
| Witness comparison (s) | 0.1116 | 0.1118 | 0.1530 | 0.1572 |
| First batch (s) | 1.5763 | 1.2688 | 1.1522 | 1.4268 |
| Worker max RSS (KiB) | 758,400 | 758,752 | 758,740 | 758,132 |
| Parent max RSS (KiB) | 1,464,824 | 1,448,268 | 1,442,628 | 1,442,624 |

Paired loop speedups: **5.97x and 6.03x**. The first baseline's compute time is
higher; it is retained in the table, not attributed to a particular cause or
discarded. The reverse-order pair independently shows the same approximate
speedup. No statistical confidence interval is claimed from four runs.

Rows are unique within a batch, recounted across batches/epochs. Each run
decoded 5,392 frames. Bytes are SDK-returned encoded PNG and array payload,
not Track bytes, physical reads or network traffic. Identity scans are outside
these payload counters but inside startup/first-batch timing. RSS values are
separate process high-water marks, not a sum of unique physical memory.

## Interpretation and limits

The combination improves this real training workload without reducing the
selected data or changing its order. Most of the observed change is inside
the SDK calls. This does **not** assign separate speedups to array concurrency
and Track reuse; no ablation was run. It also does not identify all remaining
SDK cost: 5,008 calls still consume 3.47–3.80 seconds and input waiting still
dominates. PNG decoding is about 0.45 seconds, not the main measured cost.

This is local file-backed data, smaller than RAM, with no OS-cache reset.
There is no S3/download, cold-disk, larger-than-RAM, GPU-saturation or theoretical
limit claim. Do not multiply this ratio by the earlier examples#21 ratio:
that experiment used a distributed PyPI wheel and another node/run. This
comparison uses two matching builds on one node and one fixed capture.

## Reproduction, corrections and cleanup

Use an isolated task directory. Check out the two core commits as
`core-baseline` and `core-combined`; copy this application's files to `source/`.
From the controller, install maturin 1.9.6 and pip 25.2 with `--no-deps --target
<task>/tools` (the compute-node Python lacks system pip). With Rust 1.98.1
available, submit `source/combined-build.slurm`, then submit
`source/combined-core.slurm` with `--dependency=afterok:<build-job>` from that
task root. Both builds, capture and training execute on Slurm workers.

Two script defects were corrected once: job 147599 failed before compilation
because `python -m maturin` could not find its private executable; invoke its
absolute path instead. Job 147601 compiled the baseline wheel but failed to
install because system pip was absent; use task-private pip. Their dependent
jobs 147600 and 147602 were cancelled without running. Neither failure is a
DreamDB product result. Successful wheel hashes above belong to job 147603,
not the earlier attempt.

Only source, concise measurements and reproduction are retained. Task wheels,
targets, private tools, capture/witnesses, raw logs, bundle and temporary
worktrees are removed after durable push. Shared runtime and shared caches
are preserved. Rebuilding may produce different wheel bytes; record fresh
hashes and loaded paths rather than assuming identity from the version string.
