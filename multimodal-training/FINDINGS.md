# First real multimodal training run — 2026-09-16

## Outcome

PASS. A real fixed-model mjlab Cartpole simulation produced 256 pre-action RGB
images, sensor vectors and applied-action records across eight parallel worlds
and two 16-step episodes per world. Image is a native PNG Image field; exact
sensor/action arrays and annotations use ordinary DreamDB fields. No embedding
substitute for pixels or state, private object access or core change.

After capture exited, an independent process opened its pinned Manifest. All
208 four-frame windows matched the temporary capture witnesses: ordinal and
episode/step identities, decoded pixel bytes, sensor dtype/shape/bytes and last
frame's applied action. Naive and batched reads returned identical outputs.
Whole episodes were split before windows: 156 training and 52 validation samples,
with disjoint environment/episode identities. No windows cross resets.

The image CNN plus sensor MLP trained from database outputs (not witnesses):
20 Adam updates over two epochs, finite losses, finite changed parameters, and
held-out validation MSE 0.000156336. First/last training batch loss was
0.0153500 / 0.000360093. Different batches and this tiny policy-imitation task
do not establish convergence, policy quality, image necessity or generalization.

## Measured access pattern

One local-filesystem run, same 208 sample requests in catalogue order, groups
of at most 16. Alternate which mode goes first per group; no cache reset or
statistical benchmark claim. A single-window call uses the same projected-page
reader, but cannot share pages or decoded images with neighboring samples.

| Metric | One sample per call | Batched samples |
| --- | ---: | ---: |
| SDK projected range calls | 354 | 83 |
| Rows returned by SDK | 11,266 | 2,616 |
| Returned image/array payload bytes | 28,053,416 | 6,516,317 |
| PNG decodes | 832 | 292 |
| Read/decode/assembly elapsed | 10.721 s | 2.507 s |
| First 16-sample group elapsed | 1.044 s | 0.177 s |

The measured elapsed ratio is 4.28x for this one bounded comparison, not a
production speedup promise. Both modes deliver 208 samples / 832 frame slots.
Returned NumPy output size is 10,244,416 B **calculated** from the checked shapes
and dtypes, including anchors, repeated frames, sensors and target actions.
Returned compressed payload and decoded output are different units; their ratio
is not a storage read-amplification metric. No physical disk bytes, object GET
count or network throughput was measured.

Catalogue construction took 0.242 s after Dataset open (open latency was not
separately measured). Capture loop including rendering/encoding and synchronous
publication took 4.985 s, excluding environment initialization. First training
batch load plus transfer was 0.259 s. During shuffled training, synchronous
read/decode/collation/transfer took 4.848 s versus 0.418 s synchronized optimizer
compute. This is loader-blocked wall time, not a GPU-utilization trace. Training
followed the comparison and is not cold-cache. It still spends most measured
loop time loading; the example does NOT solve large-scale GPU data supply.

Training/verification process high-water RSS was 1,526,868 KiB (about 1,491 MiB),
including Torch/CUDA runtime and small witness comparisons. This is not the
reader's isolated memory footprint, and no bounded-total-memory claim follows.
The scheduled job completed in 56 s with exit 0; generated data/caches were
removed by the coordinator. One GPU and four CPUs/16 GiB were requested; this
cluster's allocation policy assigned the whole 32-CPU node. Torch/OMP use four
threads. No cluster configuration or shared environment was changed.

## Reproduction and boundary

Source: this directory; runtime: released DreamDB 0.0.13 in private imports,
Python 3.12.3 Linux x86_64, mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1+cu128,
NumPy 2.5.3, Pillow 12.3.0, RTX PRO 6000 GPU. The original small capture's
Manifest was `dzgcesna26qcvmvxtfckco7weprrsxhhok4bi66brirpemlkth4yg`; its
temporary dataset was intentionally removed, not retained as published data.
New runs create their own snapshots and must pass their own checks.

Local Python 3.12.13 public-SDK preflight passed before GPU submission. Ruff
check/format and git diff --check passed. This is application acceptance, not
a core testbox verdict. No extra CI run was needed for investigative iterations.

Run the README commands: `run.py preflight`, then `run.py all` inside the bounded
Slurm allocation using `run.slurm`. Capture and train are separate processes;
each has a 240-second phase limit. The coordinator cleans witnesses/datasets/
caches on success or ordinary failure. Remove task staging/private imports/logs
after recording concise results. No raw logs, models, private data or credentials
are archived in the repository.

## What this says about DreamDB

Existing public APIs can support this bounded image/array/scalar application.
Coalescing reads and PNG decode reuse materially reduce repeated work. No
correctness blocker was found and no core API was patched to make this pass.

It does not establish a generic streaming scan: identity metadata still grows
with the explicit capped prefix, range calls materialize their selected pages,
and neighboring unselected rows are returned. Training shuffle reduces locality;
there is no async prefetch or cross-batch payload cache. S3, long videos/GOPs,
asynchronous sensor alignment, persistent selection plans and worker sharding
remain outside this first slice. A next core design should target genuinely
bounded multi-modality selection/delivery, rather than moving Torch or episode
semantics into the database. That is a separate capability, not claimed completed
by this reference application.
