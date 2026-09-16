# Lossless training-ready frame bank

Issue [#10](https://github.com/dreamlake-ai/dreamdb-examples/issues/10), based on
PR #9 / `a2a9e6b`. Contract and run plan written before implementation.

## Contract / layout

Output tensors are bit-identical to `cartpole-four-frame-f32-v1`: normalized
float32 [B,12,64,64] images, float32 [B,4,D] sensors, float32 [B,1] targets and
int64 [B,4] anchors. No precision change, decode, normalization, augmentation or
different shuffle. New artifact profile `cartpole-four-frame-f32-framebank-v1`
changes physical representation only, never reinterprets v1 bytes in place.

Each source anchor's frame and sensor appear once, physically ordered by
(env_id,episode_id,step_id). Five uncompressed `.npy` files: images [F,3,64,64],
sensors [F,D], anchors [F], windows [N,4] frame indices, targets [N,1]. The small
manifest retains source snapshot, sample identities and dimensions plus the
files' exact shape/dtype/size/digest. Ready manifest is written last. Fixed names,
fresh directories, no object deletion/overwrite or core lineage claim.

Within this consecutive-window profile, the four indices must be consecutive.
Pinned batch filling takes an image slice, reshapes contiguous channels as a
view and copies once per sample. Sensor and anchor slices follow the same range;
targets remain sample-specific. View creation is not pixel layout conversion.
Arbitrary requested sample order is preserved. The smaller bank may improve
locality; it is not a guarantee of a speedup or a bound on native/page-cache RSS.

## Implementation / cost boundary

For this experiment, repack the already-ready v1 artifact using mapped source
arrays, not a new database scan. Build a bounded identity/reference map and write
the bank through file-backed arrays; don't duplicate all source windows in a
Python heap. This adds repack work and transient space after the old materializer.
Report both costs honestly. Direct database-to-bank construction is not implemented
by this slice. Float32 still expands compressed images; deduplication alone will
not eliminate all source/artifact expansion.

Reuse byte delivery/digest verification, the same local trainer and model. Add a
layout choice, not another training pipeline. Local readers retain no database or
decoder handle. Keep v1 available for side-by-side measurement.

## Minimal direct evidence / bounded run

Primary claim: a smaller ready representation delivers identical actual training
inputs at comparable local-load cost. Reachable failure: wrong window/reference,
changed tensor values, reordered sample or gather slowdown. Check all small-real-
capture windows byte-for-byte against v1 and capture witnesses; GPU transfer check
and two actual epochs use the existing local trainer. No tests of this comparison
or mapping machinery. CPU preflight reaches overlapping windows before GPU work.

One eight-world/two-episode/16-step capture, v1 prepare+delivery, bank repack+
delivery, then make original database path unavailable and run both local layouts
in separate processes. Fixed v1→bank execution order; disclose warm file cache
and single-run uncertainty. Same seed/split/model/request order, 20 updates each.
No old PNG performance sweep, new network setup, repeated benchmark matrix or
additional copy controls: existing three-copy reference is sufficient.

Report unique frames versus window frame slots, artifact bytes, build/repack/
delivery time, setup/first batch, host gather, completed H2D, compute and peak RSS.
One Slurm GPU, four CPU/16 GiB requested, ten-minute job limit, 240-second phases.
No production data, shared-runtime mutation, package release or automatic merges.
Clean generated data/artifacts/witnesses/cache and task staging/worktree after
preserving source, conclusions and reproduction.
