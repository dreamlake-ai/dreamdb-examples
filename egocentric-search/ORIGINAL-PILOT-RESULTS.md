# Original-only source-frame pilot — 2026-09-18

Slurm **148008**, COMPLETED / exit 0, elapsed **8m23s**, RTX 5090 on
bos14-node-099. Eight CPUs / 32 GiB requested; not measured utilization limits.
Same frozen eight source shards, 58 selected clips; no corpus expansion.
Runner implementation: ingest commit `9c898ec`, private core
`0df51db7b2d2ae51ae219cb53a2936e91926e98e`, wheel SHA256
`8618af52b1682e1a2babe695adbb38da39fc5f716ea19f774a55980b61b54d6e`.
The installed package says 0.0.14 but this is NOT the released 0.0.14 build.

## Outcome

- Ref: `ego100k-original-148008`, in the existing private task bucket.
- Manifest: `d3zjkyj2hwkzt5nosibogh5x6wxpujgw3x32vuqb4gaashzpatka4`.
- 8 units, 58 VideoItems, 10,440 source-frame vectors, zero skips.
- Original codec stream-copy fragments, per-item init; no previews or lexical
  indexes. Container bytes change; original-file byte identity is not claimed.
- Calibration: k=102, all 10,440 samples; vectors published in one chunk.
- Reopened dataset: all 58 items passed one interior-window read, checking exact
  init/fragment digests and item anchor. Total returned bytes: 34,142,209.
  This is not a full-fragment readback or browser playback test. The separate
  two-real-clip full decoded-frame check remains in PATCHED-RESULTS.md.
- Four real text prompts, two passes, top_k=10 / nprobe=32 / empty projection:
  each returned ten anchors; per-prompt anchor order matches across passes.
  Measured query range 0.841–1.757 seconds. Not relevance, recall, or concurrency
  proof; neither pass is asserted to be a controlled cold-cache measurement.

Stored media payload is **728,555,383 B**, versus the historical selected source
MP4 total 728,331,965 B: +223,418 B (about 0.031%) for remuxed init/fragments.
The **1,316,517,665 B preview derivative is not generated**. These byte counts
exclude manifests/indexes/history and do not report total bucket occupancy.
Existing retained baseline data was not deleted.

## Timing and remaining bottleneck

| Phase | Seconds |
|---|---:|
| Acquisition through media/metadata ingest | 415.749 |
| Of that: catalogue wait | 125.784 |
| Of that: stream-copy remux | 1.745 |
| Of that: 58 VideoItem publications | 210.978 |
| Of that: original decode/sample | 62.076 |
| Of that: GPU encode | 5.388 |
| Of that: 8 additional append/commit calls | 7.999 |
| Calibration | 6.881 |
| Vector layer publication | 33.679 |
| Reopened media range readback | 13.813 |

Subphase timers do not exhaust every overhead and are not HTTP counters.
One-shard prefetch overlaps acquisition with current processing.
The largest measured application phase is VideoItem publication, not GPU
embedding or remux. A future batching investigation should target that boundary;
these numbers alone do not identify its internal request amplification.

This is **not an end-to-end speedup claim** over the earlier 365.632-second
optimized preview pipeline: source pixels, storage representation, SDK and
network/cache conditions differ. The fixed-work batching result is a separate
experiment in BATCH-RESULTS.md. Same-Ref small-batch fairness remains unresolved.

## Reproduction and retention

Deploy ingest `9c898ec`, retain the pinned wheel, then use
`spaces/ego100k/submit_pilot.py --task original`. It creates a new Ref and uses
the frozen selection, pinned model and `embedding-original.json` spec. It does
not resume the measured Ref or modify the shared PyTorch environment.

Small result: `/home/tom/ddb-ego100k-400/runs/148008/pilot-result.json`, copied to
`/Users/locatino/fortyfive/artifacts/ego100k-400/original-pilot-148008.json`.
The run's source-derived vector shards, calibration, and per-item publication
records remain for subsequent write/read experiments without repeating encoding.
Cleanup Slurm 148009 confirmed removal of the two exact task scratch directories
(41 MiB batch dependencies + 1,002 MiB pilot dependencies/model/cache). No jobs
remain. The 31 MiB run directory is retained for those next experiments. The
private wheel, exact reader and unfinished task worktrees remain; no S3 deletion
or GC, no production Ref changes, no package release or CI run.
