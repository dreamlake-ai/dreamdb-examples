# Workload contract

## Claim and observable failure

Measure real semantic-query saturation and committed write goodput without
reducing query coverage or losing acknowledged records. The minimum evidence is
actual SDK operations, backend request counters and a fresh reopen/readback of
acknowledged records. Missing/changed acknowledged data, silently overwritten
concurrent writes, unreported timeouts or mismatched query outputs fail the run.
No controls for controls, mutation harness or synthetic performance assertions.

## Input and identity

Source `builddotai/Egocentric-100K`, revision
`fae604b751b25337d6fd8c4c53e595910c28f68f`. Select across actual factories and
workers, record source path and blob identity/size. No inflated corpus from
duplicate samples. Original clip/member identity and frame timestamp survive
transcoding. Use disjoint explicit anchors for different writers; retry the same
logical records rather than assign new identities after a conflict.

Image and text encoding use `google/siglip-base-patch16-224` revision
`7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed`, matching pinned preprocessing and
normalization. Start at 1 frame/second. Final dependency pins and encoding/index
parameters must be recorded before a GPU run; model choice is not a claim of
optimal relevance. Real diverse text queries are encoded outside DB timings.

## Persisted data

- Original video: persist the exact MP4 bytes in the private task S3 bucket, with
  source revision/member identity, byte length and content digest. Preserve for
  future experiments; a remux or transcode is not the original. Do not upload
  whole source TARs merely to preserve their contained MP4s.
- Preview: separately encoded, labelled derivative with explicit codec, rate,
  resolution and timestamp mapping, linked to its original. Transcode cost and
  byte size measured. Both original and preview are retained, not alternatives.
- Frame embeddings, supported index/compressor/exact-rerank dependencies and
  necessary provenance/clip metadata: persisted through DreamDB public APIs.
- Raw-video download/upload, decode, preview generation and embedding inference
  are measured separately from DreamDB write throughput. Report original and
  preview bytes separately, as well as total persisted storage.

## Read matrix

Pin SDK and snapshot; fix top-k/nprobe/rerank/projection across comparisons.
Measure retrieval-only separately from selected metadata and preview fetching.
Separate metadata/object/backend caches; do not flush shared OS caches or call
a fresh process a cold backend. Compare varied queries and identical repeats.
Start concurrency 1/2/4/8/16, with explicit duration, request/byte caps and timeout
chosen from pilot measurements. Record QPS, p50/p95/p99 with sample counts,
timeouts/errors, backend operations/bytes, RSS/CPU and offered/completed load.
Closed-loop throughput is not an open-loop latency guarantee.

## Write matrix

Use separate processes/handles, not a shared mutable Dataset behind a lock.
Precomputed real payloads are identical across comparable runs; each run has
fresh isolated Ref names. Record records/s, committed MB/s, commit latency,
PUT/GET/HEAD counts, retries/conflicts, attempted/persisted bytes and peak memory.
Specify whether bytes count logical payload, encoded data or actual traffic.

1. Independent Ref per writer: raw aggregate goodput. If consolidation is tested,
   measure merge/final visibility separately and include it in end-to-end goodput;
   branch-local success is not visibility in a single final dataset.
2. Same Ref: expected optimistic CAS contention. Separate first-attempt success,
   explicit publish conflicts, bounded reopen/retry, timeout/unknown outcomes and
   final acknowledged goodput. Never force overwrite to make conflicts disappear.
   Do not promise automatic SDK retries; inspect the actual version's contract.
3. Fresh reopen: compare acknowledged stable IDs/anchors and payload digests,
   detect duplicates and unexpected/missing records. Unknown publication outcomes
   must be reconciled before retry to avoid counting duplicate writes as progress.

Read and write baselines run separately first. Mixed read/write is a later matrix
after isolated results, not a hidden source of interference. S3 is the measured
storage backend, not HF. Private dataset permissions remain intact.

## Limits

Pilot: 1 GPU, 8 CPUs, 32 GiB RAM, 2 hours, <=8 GiB source shards, <=64 clips,
<=4 video hours, <=32 GiB local artifacts. Limits are stop conditions. No automatic
million-vector expansion or full-corpus import. No production Ref moves, public
ACLs, cross-user credentials or unbounded retry loops. Original-video upload is
authorized within the bounded pilot; retaining it does not authorize full import.
