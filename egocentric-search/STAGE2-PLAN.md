# Stage 2: bounded extension to 10,000 unique clips

2026-09-20. Owner's “继续” following the explicit stage-2 budget authorizes
continuation within that envelope. It does not remove the admission limits.
No stage-2 data job has been submitted at this update.

## Binding and limits

- Continue `ego100k-ingest-v1`, starting from accepted tip
  `dzwazfxlkudoyi2qclo56cvcxu75keblma42tfur65lvrglz5huku` (1,000 clips).
- Cumulative coverage target 10,000: admit at most 9,000 new identities.
  Keep the first 1,000 ordinals/anchors; never rebuild them from a reordered list.
- At most 4 concurrent GPUs, 100 incremental reserved GPU-hours, 256 GiB
  incremental source transfer, 64 GiB node scratch per worker. Request/egress
  review budget $40; this is not an AWS-enforced spending limit. Existing storage
  charges and full-corpus review ceilings remain in FULL-INGEST-BUDGET.md.
- Same pinned HF revision, SigLIP model/spec, original H.265 stream-copy items,
  no preview/lexical index, exact vector sidecars retained.
- Every job gets a fixed qualified SDK artifact, source identity and resource
  admission entry. No in-place upgrade of a live worker.

## Execution shape

Separate bounded source/media/embedding producers from one controlled publisher
for the corpus Ref. GPU work must not wait synchronously on every metadata CAS.
Do not implement this by letting four independent Dataset handles blindly append
to the same Ref. Same-Ref contention testing is a separate bounded experiment,
not the normal ingest retry policy.

1. Freeze the source admission ledger, reuse verified partial TAR contents before
   downloading again, deduplicate full `(revision, shard, member)` identities.
   Count input reservations before download, including failed requests; no hidden
   filtering of unsupported clips.
2. Producers create immutable per-unit artifacts and ready records. Queue bounds
   must be **bytes as well as item counts**, including fragments and vectors.
   Stop admitting work on backpressure; do not accumulate 10K clips in RAM/shared
   scratch. Keep exact payload hashes, input/spec identity and anchor windows.
3. One publisher owns the SDK handle, Ref and durable CheckedWriter journal.
   Publish media before dependent metadata/vectors, coalesce metadata when safe,
   acknowledge units only after all required commits. Release staged bytes only
   after durable acknowledgements. Unknown ordinary commit outcomes still stop;
   checkpoint recovery uses the persisted exact plan, never a replacement tip.
4. Append vector chunks to the existing indexed field and reuse its explicit
   stored SI/compressor. Do not silently retrain/replace the index or mix vector
   specifications. Stage-1's 423-centroid index is not evidence of suitable
   full-corpus recall or cost: record query/maintenance behavior as it grows;
   an index replacement requires its own explicit migration plan.
5. Measure 1-worker then bounded multi-producer throughput on admitted data,
   preserving one searchable Ref and exact counts. Four successful workers alone
   are not proof of speedup. Count retries, conflicts, transferred/stored bytes,
   queue high-water bytes, publication time and allocated time by phase.

## Implemented first slice: bounded vector publication input

`dlingest.vector_stream.VectorStream` reads immutable ShardSink files in frozen
clip order, validates NPY shape/dtype/length before materializing numeric payload,
enforces 3,600 rows per shard and ordered disjoint anchor windows, then emits
16,384-row batches. It preserves the old SHA256 of all anchors followed by all
vectors using two bounded passes, and preserves the final short-batch resume
offset. The existing stage-1 script now consumes this reader instead of
concatenating corpus-sized arrays. Its 1,000-clip admission cap is unchanged;
this code change does not itself launch or admit stage 2.

Direct checks:

- Unit suite: 248 passed / 1 skipped / 11 integration deselections.
- Existing real H.265 + IVF/checkpoint integration suite with registry Python
  0.0.15: 3 passed, including actual batch publication, reopen and offset resume.
- CPU-only Slurm 148470 read the already-created stage-1 artifacts: 179,774
  vectors, legacy digest exactly equal to the durable checkpoint, 11 batches,
  largest 16,384 rows. 7.306 s, whole-process max RSS 134,636 KiB (~131.5 MiB).
  No S3 writes, no new source downloads and no GPU. This is a local/NFS input
  measurement, not S3 publication speed or a publisher/GPU memory bound.

## Remaining before data launch

Producer/publisher separation, byte-bounded queues, stage-2 admission/credential
submission and real request telemetry are NOT implemented by the vector reader.
Python currently exposes semantic-cache stats but no complete HTTP attempt/
retry/byte counters. Python method-call counters cannot fill that gap; instrument
the real connector send/retry boundary and expose bounded aggregate statistics,
without recording credentials, signed URLs or request headers. Do not enable
bucket logging services or infer billing from application calls.

Reuse the existing public-boundary checks for controlled publication/reopen and
uncertain-commit recovery; do not introduce a second validation framework.
After remaining implementation and qualification, start inside this approved
envelope without asking again for the same budget. Stop for a genuinely new
data/semantic loss, incompatible SDK, or an exceeded resource envelope.
