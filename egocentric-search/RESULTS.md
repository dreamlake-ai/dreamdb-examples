# Bounded Egocentric-100K results — 2026-09-17

Issue: [core #400](https://github.com/dreamlake-ai/dreamdb-core/issues/400).
This is a real-data pilot, not a full-corpus ingest or saturation certification.
All timed cloud workloads below used released **dreamdb 0.0.14**, Slurm node
bos14-node-099, and the dedicated private us-east-1 S3 bucket in PLAN.md.
No production Ref changed. No lexical index was built.

## Input and ingest

Source revision `fae604b751b25337d6fd8c4c53e595910c28f68f`; eight known-size
shards, 6,046,627,840 source bytes; 58 actual clips, 10,440 actual frame vectors,
zero skips. SigLIP revision `7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed`, 1 fps;
RTX5090, torch 2.9.1+cu128, transformers 4.57.6. Both exact original MP4s and
456x256/30fps H.264 previews are retained. Original 728,331,965 B, preview
1,316,517,665 B: preview is larger, not a claimed storage saving.

| Slurm job / variant | Main ingest loop | Media append time | Append calls |
| --- | ---: | ---: | ---: |
| 147824 serial / per clip | 564.807 s | 132.678 s | 58 (per-clip path) |
| 147828 one-shard prefetch + 128 MiB logical batches | 365.632 s | 88.534 s | 22 |
| 147833 additionally one-preview lookahead | 406.778 s | 94.199 s | 22 |

147828 is 1.545x faster in this observed pair. All 10,440 anchor/vector records
matched byte-for-byte across all three runs; all original/preview digests passed.
No controlled network/cache equivalence: catalogue/acquisition wait was
230.388 / 76.145 / 169.658 s respectively. Lookahead has not demonstrated an
additional wall-time benefit, remains opt-in. Overlapping timers are not additive.
Calibration ~1.5 s, vector publication ~4.7 s. SDK calls are NOT HTTP counts.

## Vector writes: batching matters more than adding publishers here

Fixed 512 actual precomputed vectors, exact rerank sidecars and scalar identity;
fresh Dataset/Genesis per case. Ref creation and readback outside reported time.
All successful cases reopened and reconciled every acknowledged anchor, digest
and exact f32 vector. Ordinary Python scans return lossy reconstruction, so
exact verification used the existing release-tag `dump_exact_subset` CLI.

Independent Refs, batch 32, job 147830:

| Writer processes | 1 | 2 | 4 | 8 | 16 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Seconds, including process startup | 20.620 | 10.638 | 5.740 | 3.465 | 3.083 |

Every level passed, zero conflicts. Independent-Ref throughput is NOT a merged
dataset result; the known layer-parent consolidation incompatibility remains.

Single writer, job 147834:

| Records per commit | 32 | 128 | 512 |
| --- | ---: | ---: | ---: |
| Seconds, including startup | 21.602 | 5.149 | 1.554 |
| Successful commits | 16 | 4 | 1 |

All passed. 13.9x observed improvement from larger batches on this small payload;
not a universal batch size or network-limit claim.

Same-Ref contention is distinct:

- Short backoff, two writers (147830): 256 acknowledged, five explicit conflicts,
  one exhausted writer; STOP, all acknowledged data intact. No escalation.
- Seconds-scale randomized backoff, still five attempts/batch (147834): two
  writers passed, 512 acknowledged, four conflicts, 27.227 s. Slower than the
  one-writer batch-32 run; retries do not imply throughput improvement.
- Four writers: 384 acknowledged, seven explicit conflicts, one other error;
  STOP, exact reconciliation issues empty. Error was S3 HTTP 409 with Code
  `ConditionalRequestConflict`, Condition `If-Match`. SDK exposed Backend rather
  than its publication-conflict result. Eight/sixteen writers were not attempted.

Core fix is isolated in branch `fix/400-s3-cas-conflict`, commit `8679b25`:
recognized S3 If-Match 409 becomes CasFailed; unrelated/create-only 409 remains
an error, no stale replay. Native connector boundary suite: 25 passed. Not yet
testbox-qualified, merged, released, or used in these cloud numbers.

## Actual original + preview write payloads

Job 147838, first 16 distinct clip pairs by anchor from the verified pilot,
**569,541,414 logical bytes per level**. One clip per commit, independent Refs,
fresh timelines. Preload, Ref creation and verification excluded from write
window; startup/local-load-inclusive seconds also retained in the result JSON.
Every original and preview was reopened and digest-checked at every level.

| Writers | 1 | 2 | 4 | 8 | 16 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Write window seconds | 17.831 | 13.305 | 9.536 | 8.407 | 6.533 |
| Logical media MiB/s | 30.46 | 40.82 | 56.96 | 64.61 | 83.14 |

All levels passed. 2.73x observed aggregate goodput, not 16x; 16 clips is short
and heterogeneous, not a sustained link-saturation measurement. Does not include
branch consolidation. Logical bytes exclude protocol overhead/retries/outboards.

## Semantic retrieval and hit-to-video

Four genuine text prompts, two passes, ten hits per prompt passed on 147825.
This repaired a missing SentencePiece environment dependency after 147824;
no reingest. Functional queries, no labeled recall or relevance score.

147836 retrieval-only stress: four actual image embeddings, 64 closed-loop
queries/level (320 total), pinned pilot tip, top-k=10, nprobe=32, projection=[].
Every result's anchors/order matched the serial baseline. Not text-query
relevance evaluation and not a cold-cache test.

| Readers | 1 | 2 | 4 | 8 | 16 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Completed queries | 64 | 64 | 64 | 64 | 64 |
| QPS within query window | 1.117 | 2.216 | 4.312 | 8.700 | 15.478 |
| p50 ms | 694 | 702 | 714 | 692 | 727 |
| p95 ms | 1603 | 1559 | 1712 | 1761 | 1861 |

Zero errors/mismatches. At most 58,376 KiB per-worker process high-water RSS on
Linux (not aggregate simultaneous RSS). Empirical p99 is in the raw result, but
64 samples/level is too small for a tail-SLO claim. Repeated-query/shared backend
caches were not reset. HTTP counts and traffic remain unmeasured.

147835 resolved one real text-query hit at offset 175 s to its 179.734 s clip
using the application hour-stride convention. Read and verified 12,069,907 B
original + 22,699,191 B preview in 1.459 s. This checks the application lookup;
not automatic temporal hydration, range seeking or playback-start latency.

## Interpretation and unfinished scope

- Prefer batching and overlapping preparation before multiplying same-Ref
  publishers. Independent writers scale, but do not solve final consolidation.
- Same-Ref CAS classification has a real repair, but the patched cloud result
  is not established. Fairness under bounded retries is not guaranteed.
- No claim that request counts are minimal, the network is saturated, or a
  10,440-vector pilot predicts million-vector query behavior. Real HTTP counters,
  sustained larger-corpus workloads and formal qualification remain separate.
- No automatic 1M/10M/full-corpus ingest under this pilot budget.

## Reproduction and retention

Ingest branch `feat/ego100k-pilot` commit `270e174`; examples workload commit
`891d806`. Read SPEC/PLAN and per-repo README for exact scope, runtime and
commands. Slurm jobs ran sequentially. After tune STOP, only the independent
read/media jobs were released (`147835` afterany rather than afterok); no failed
write strategy was escalated. No CI was triggered.

Concise JSON outputs and exact source selection are in local
`/Users/locatino/fortyfive/artifacts/ego100k-400/`; remote task root is
`/home/tom/ddb-ego100k-400`. Cleanup status/necessary retained paths are recorded
in PROGRESS.md. Private source videos, credentials and raw logs are not checked
into Git. Private S3 datasets are intentionally retained, with no deletion/GC.
