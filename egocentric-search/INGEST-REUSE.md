# Reuse decision: dreamlake-ingest

Inspected remote default branch at
`dreamlake-ai/dreamlake-ingest@dd60641a8e317933e79f960a9ca30a177d03bf99`.
The requested name dreamdb-ingest did not resolve in this organization; the
existing local checkout points to dreamlake-ingest. This is a source review,
not a successful runtime qualification.

## Reuse rather than duplicate

- `dlingest/adapter.py`: Unit/Candidate/Item and enumeration/catalogue/fetch/items
  boundary. Implement a new `spaces/ego100k` adapter here, not another ingest
  orchestration in examples.
- `fetching.py`, `sampling.py`, `state.py`, `run.py`: bounded acquisition,
  duration-aware selection, resumable per-unit work, phased processing.
- `media.py`, `cmaf.py`, `embed.py`, `sinks.py`: preview handling, SigLIP image/text
  encoding and staged vectors; reuse with the adaptations below.
- `calibration.py`, `layers.py`, `backend.py`: train from actual vector counts,
  publish layers, branch writers and merge. Preserve small-sample constraints.
- Existing Slurm patterns: reference only, not unchanged 40-node launch scripts.

## Required adaptations before a real run

1. **Source adapter and pin.** Existing ego10k regex expects
   `factory_N/workers/worker_N/..._partN.tar` and uses `resolve/main`.
   100K tree actually has `factoryNNN/workerNNN/partNNN.tar`. Consume the pinned
   bounded selection manifest; do not scan/download the full corpus implicitly.
2. **Current SDK qualification.** pyproject still pins dreamdb==0.0.7; integration
   test prose even references 0.0.5. Select a current pinned build and run the
   smallest existing real-engine path before claiming compatibility. Historical
   README numbers or labels do not establish today's behavior.
3. **Preserve originals.** `run.py` RAW calls `ds.ingest_video`, whose current SDK
   contract remuxes MP4 into CMAF init/fragments. This does not preserve exact
   original file bytes. Add exact-original storage with source identity/digest,
   and separate the preview path. Existing ego10k schema declares video_raw h264,
   whereas 100K source is H.265; do not inherit that schema blindly.
4. **Preview and model config.** media.py fixes 854x480/30fps; source is 456x256.
   Avoid mandatory upscaling, while preserving a consistent per-track config.
   embed.py from_pretrained currently lacks revision arguments: bind both model
   and tokenizer to the benchmark's pinned revision. No forced new encoders.
5. **Private S3 and measured writes.** Existing presign support is useful, but its
   preflight's 'round-trip' currently only performs PUT. Verify actual signed SDK
   write + reopen/read on the isolated bucket. Do not convert it to public access.
   `merge_branches(..., drop=True)` deletes branches by default: preserve trial
   branches until results are recorded; never reuse broad production prefixes.

## Benchmark boundary

Ingest supplies real prepared inputs. A thin independent runner measures actual
SDK reads/writes and backend operations. Existing branch fanout covers independent
writers, not the same-Ref CAS stress case: measure that explicitly with bounded
reopen/retry and acknowledged-record readback. Encoder/transcoder timing stays
outside DB goodput. Do not fork the phase library merely to add timing.

The local shared ingest checkout has unrelated uncommitted changes in verbs.py,
spaces/ego4d/space.py and an ego4d-imu Slurm directory. Preserve it. Any adaptation
must use an independent worktree from the pinned remote revision.

## Current preparation, not a benchmark result

Eight selected shards from eight spread-out factories total 6,046,627,840 bytes;
selection fetched metadata only, no video. Manifest is retained at
`/Users/locatino/fortyfive/artifacts/ego100k-400/pilot-inputs.json`.
The dedicated S3 bucket is created and its public-access block, SSE-S3 and owner
enforcement read back successfully. No video data uploaded, no compute job run.
