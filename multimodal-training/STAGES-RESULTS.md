# Two-stage result — 2026-09-16

PASS on the same actual 256-record Cartpole capture, released DreamDB 0.0.13,
Python 3.12.3, mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1+cu128, NumPy 2.5.3,
Pillow 12.3.0, Linux x86_64 / RTX PRO 6000. One Slurm job, exit 0, 65 s total.
Four CPUs/16 GiB requested, whole 32-CPU node allocated by cluster policy;
Torch/OMP use four threads. No shared environment or core changes.

## Upstream materialization and delivery

The source Manifest was
`d3mpxicds66jdewlzb6lwacfbbiidecyebk6jlcjiuezudvct7x4o`. It and its data were
task-private and cleaned, not published as a persistent dataset. Reproduction
creates a new snapshot and checks that run independently.

| Operation | Measured |
| --- | ---: |
| Snapshot open / catalogue selection | 0.233 s |
| Projected read and PNG decode | 2.376 s |
| Profile conversion / layout | 0.00968 s |
| Tensor file write + hash | 0.643 s |
| Total materialization | 3.264 s |
| Original backend, all files incl. metadata/history | 856,034 B |
| Ready artifact incl. manifest | 40,934,870 B |
| Local delivery of 52 tensor files, copy + hash | 0.497 s |

The artifact is **47.8 times the size of this source backend**, not a pure codec
compression ratio: source includes indexes/history, while artifact repeats
overlapping windows and expands pixels to float32. It contains 208 complete
four-frame samples in 13 shards. Delivery payload is 40,921,920 B plus manifest.
No PNG decode or normalization occurs in delivery. Local copy/hash is not a
network download measurement or a claim of crash-durable fsync.

This is a workload-dependent trade: reusable preprocessing and more stored/
downloaded bytes buy less per-epoch work. No end-to-end claim should omit the
3.264 s build or 0.497 s delivery, and remote bandwidth could reverse the trade.
MinIO/network saturation was deliberately not made a dependency; local loading
was the user's priority.

## Local inputs actually ready for compute

The original database path was renamed out of service before the independent
local trainer started. All 208 ready windows matched capture witness identities
and the declared float32 profile. The profile uses explicit float32 multiplication
by float32(1/255); old PNG training used a device-side division. Numerical training
trajectory equivalence is not a contract between those operations.

One completed GPU batch copy matched its pinned source tensors exactly. Both
paths trained the same shared model, using 156 training / 52 validation samples,
the same episode split, seed, shuffled request schedule, two epochs / 20 updates.
Finite changed parameters and validation passed. Local validation MSE was
0.000156335646. This is pipeline acceptance, not expert-policy quality.

| Training-loop input work (20 batches) | Original PNG path | Ready tensors |
| --- | ---: | ---: |
| Load / decode / convert / transfer, GPU-ready wall time | 4.803 s | 0.00632 s |
| Ready tensors: host sample gather | — | 0.00290 s |
| Ready tensors: H2D submission through completed event | — | 0.00342 s |
| H2D CUDA event duration (subset of preceding wall time) | — | 0.00307 s |
| Synchronized optimizer compute | 0.494 s | 0.237 s |

The input-loop ratio is about 760x for this one run **after materialization**,
not a 760x training/job speedup or a claim that DreamDB storage itself got faster.
Different compute times are reported, not attributed to the data path.
Train-ready transfer volume was 61,362,912 B across 312 requested samples,
averaging 15.6 samples/batch. There is no decode/float conversion/layout transform
inside the local loop. Host gathering still copies shuffled samples; H2D remains.

Initialization is not free: mapping/shape checks took 0.0721 s; Torch/CUDA/model/
buffer/optimizer setup including mapping took 2.036 s. Acceptance-only witness
comparison took 0.0604 s and warmed file pages before training. First local batch
gather + completed H2D took 0.573 ms; later results do not conceal it. Original
path first input took 0.261 s. Both paths ran after other reads of the small
capture; original ran first. No cold-cache or repeated-trial confidence claim.

Training/verification process peak RSS: 1,614,936 KiB for ready tensors versus
1,591,936 KiB for original. These include Torch/CUDA and witnesses, not isolated
loader footprints. mmap's virtual mapping does not bound resident file cache.

## Distance from a load-only reference

Three warm copies of the same 16-sample contiguous ready batch into pinned memory
then GPU took 0.229 / 0.186 / 0.182 ms. The actual shuffled local path averaged
0.316 ms over 20 batches (including its first batch, and two shorter batches).
This shows the local path is of the same order as direct copy, with remaining
gather/per-sample dispatch and memory-locality cost. It does not prove the hardware
theoretical limit or a statistical performance bound. Aggregate H2D event timing
corresponded to about 20.0 GB/s for this small warm transfer workload; it is not
a sustained PCIe benchmark. No extra tuning or control framework was added.

## Reproduction and cleanup

CPU: `python -B pipeline.py preflight` in the documented storage environment.
GPU: `python -B -u pipeline.py all` inside the same bounded Slurm allocation as
README; install released SDK only in private imports when reusing shared runtime.
The coordinator sequences original capture/train → prepare → local delivery →
source-path removal → verification/local train in separate processes, with a
240-second phase timeout. Plain `train-local` needs only delivered files, not
witnesses; `verify-local` is the explicit acceptance-only mode.

Preflight, Ruff check/format and git diff --check passed. No core testbox verdict
or new CI is claimed. Coordinator cleaned generated datasets/artifacts/witnesses/
caches; task-specific imports, source staging, logs and worktree are removed after
durable source/result preservation. No raw training data or logs are archived.
