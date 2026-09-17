# Training-ready materialization and two delivery stages

Issue [#8](https://github.com/dreamlake-ai/dreamdb-examples/issues/8), stacked on
PR #7 at `b838dfc`. Written before implementation. Local device loading is the
priority; MinIO/remote network saturation is not a prerequisite or current claim.

## Contract

The upstream **materialize** operation turns the fixed snapshot and exactly the
same ordered samples/split into a new immutable application artifact. Profile
`cartpole-four-frame-f32-v1` specifies float32 images [N,12,64,64], frame-major RGB
channels, each pixel multiplied by float32(1/255), float32 sensors [N,4,D], float32
targets [N,1], int64 anchors [N,4]. Train/validation episode split is unchanged.
No image decode, normalization, transpose or dtype conversion remains in train.
Changing profile or samples requires a new artifact, never reinterpret old bytes.

Each shard holds at most 16 complete samples in uncompressed `.npy` files,
allow_pickle=False. Manifest contains source snapshot/receipt, profile, exact
sample identities, metadata, shapes/dtypes, filenames/sizes/digests. Fixed names
only, no executable content. Manifest is published locally last; partial builds
are not ready. Never overwrite an existing destination. Original DreamDB objects
are not changed and artifact is not registered as a core format or fake lineage.

**Stage 1 / delivery** copies or downloads these already-ready files and verifies
their digests before publishing its local manifest. It does not build them from
PNG during timed download. A simple local copy is enough for this slice; storage
transport optimizations and MinIO are optional later. No claim about network rate.

**Stage 2 / train-local** uses only the delivered directory. Map arrays read-only,
gather arbitrary requested samples directly into reusable pinned CPU batch buffers,
then copy to GPU without decoding/conversion. Record GPU completion before calling
it device-ready. mmap defers page faults, not IO; shuffle still needs gathering.
This synchronous slice does not claim GPU-direct storage or overlapping compute.
The artifact is trusted after verified delivery; local mmap opening checks declared
shape/dtype but does not rehash all bytes on every epoch. User mutating local
artifact bytes after verification is outside the immutable artifact contract.

Fully materialized windows duplicate overlapping frames and expand compressed
images. Measure artifact size and materialize cost; this trades upstream storage
and download bytes for repeatable low local CPU preparation. It is not necessarily
best time-to-first-sample or cheapest overall. Dynamic augmentation remains outside
this fixed profile and would add work; it is not silently precomputed away.

## Plan / minimum evidence

1. Add `stages.py` (materialize/deliver/LocalBatches) and local-train entrypoint,
   reusing the existing model and capture. Keep the original PNG route for
   comparison. No core change or generic cache/download service.
2. CPU preflight: small real SDK fixture → artifact → verified local delivery →
   mmap values match original samples under the documented profile. No framework
   for testing the checker or adversarial mapping matrix.
3. One Slurm job: same 256-row real capture; original read/train; materialize;
   local delivery; rename original backend out of the expected path; new local
   trainer process. All ready values/anchors compared directly with temporary
   capture witnesses, then exact device transfer checked once at the real boundary.
   Run two epochs / 20 updates, finite changed parameters and validation.
4. Separate materialize selection/read/decode/transform/write costs and artifact
   bytes, delivery copy/hash time, map initialization, host gather, completed H2D,
   compute. First batch is not hidden. Compare original/local routes on the same
   capture, but report fixed execution order and uncontrolled file cache state.
5. To contextualize 'load-only', measure three repetitions of one ready contiguous
   batch copied to pinned memory and GPU, as a warm copy reference. This is an
   attainable baseline, not theoretical PCIe/DRAM limits. It directly distinguishes
   loader overhead from unavoidable copying; no additional control layers.

Use existing Slurm bounds (one GPU, four CPU,16 GiB, ten minutes), separate capture/
trainer processes with 240-second phase limits. Dataset/witness/artifact/cache are
task-private, cleaned by coordinator. No shared runtime mutation, production data,
package release, automatic PR merge or redundant core CI. Retain concise results
and reproduction, not raw artifacts/logs. Stop after this measured slice; don't
assert theoretical optimality from a small warm-memory experiment.
