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

## Implemented second slice: standalone bounded disk handoff

`spaces/ego100k/handoff.py` at commit `f902301` on `feat/400-bounded-handoff`
implements the disk-backed lease table described below as a standalone module:
a single small JSON state file under the spool root, guarded by `fcntl.flock`
and mutated only by short read-modify-write transactions that are never held
across hashing, deletion or producer/publisher work. Capacity is reserved
before a producer writes its first byte; reserved, ready and
claimed-unacknowledged units all hold it, so consuming a ready unit frees
nothing and an unacknowledged publication keeps blocking admission.

Direct checks, independently re-run by the lead: 251 passed / 1 skipped / 11
integration deselections. No stage-2 integration, NFS, Slurm or performance
claim is made for this slice. One fixture correction is recorded here: the
child processes are released through a FIFO read on a raw file descriptor of
exactly one byte, because a buffered read would drain the other children's
release bytes.

Purpose and limitations:

- The reservation is a *trusted peak* declaration, not a filesystem quota.
  Nothing observes the unit directory between reservation and `ready`, so a
  producer that transiently exceeds its bound and cleans up still passes the
  end-of-production measurement. It bounds producer-owned files under the spool
  root only, never GPU, decoder or SDK memory.
- `flock` is exercised between local processes on one node. Nothing about NFS
  or multi-node locking is validated by this module or its tests.
- Remote acknowledgement truth remains CheckedWriter's journal. `acknowledge`
  records the caller's asserted receipts for media, metadata **and** vectors
  plus the tip the caller confirmed; it proves no commit of its own.
- Completion is a durable per-identity receipt file, deliberately not a list
  inside the state file that would grow to corpus size. A completed identity is
  refused forever, so cleanup cannot turn a finished unit back into admittable
  work.
- A producer that overruns its reservation closes admission for *every*
  producer until an operator reconciles it; the bytes are already on the disk.
  Nothing here expires leases, retries, or reclaims abandoned reservations.
- Cleanup order is deliberate and safe to retry: delete the unit directory,
  sync, record the completion receipt, and only then free the capacity.
  Freeing first would admit the next producer against bytes still on the disk.

Not implemented by this slice: producer/publisher wiring into the stage-2
pipeline, bounded vector publication epochs, and stage-2
admission/scheduler/HTTP telemetry. This slice launches nothing, uploads
nothing and makes no throughput claim.

## Remaining before data launch

### Delegated implementation boundary (2026-09-20)

Claude Code performs scoped implementation; the lead reviews code and evidence
and retains deployment/merge authority. The first read-only proposal was not
approved unchanged: a thread-only driver does not establish multi-process
handoff; blocking reservation on the consumer thread can prevent the consumer
from releasing capacity; deferring every vector until corpus completion retains
corpus-sized artifacts. The existing stage-1 loop is not being replaced yet.

The first authorized implementation slice is a disk-backed handoff in the
ego100k adapter, isolated at `feat/400-bounded-handoff` from `d566652`:

- Reserve both bytes and an item before producer work; nonblocking admission
  lets the eventual coordinator consume rather than wait on its own budget.
- Reservations cover declared producer-owned files while producing, ready,
  and awaiting acknowledgement. They do not promise a GPU/decoder/SDK memory
  bound. Stable ready bytes survive failure; there is no automatic lease expiry.
- Only an explicit acknowledgement after media, metadata **and vectors** have
  durable publication receipts permits cleanup/release. The handoff itself
  cannot establish that a remote publication succeeded; CheckedWriter remains
  authoritative for that boundary.
- Local separate-process checks establish local admission/ownership behavior,
  not Slurm/NFS qualification or ingestion speedup.

Existing decisions are unchanged: extend the same Ref with its stored index;
256 GiB is incremental **source** transfer, not a combined download/upload cap.
New vectors need bounded publication epochs with independent digests/offsets:
do not append new shards to stage 1's stream and reinterpret its terminal short
batch offset. The epoch driver, source admission, multi-node coordination and
HTTP telemetry remain separate unfinished integration work.

The vector reader implements none of the following, and the handoff slice above
is a standalone module that is not yet wired into the pipeline: the byte- and
item-bounded queue now exists and is directly tested in isolation, but
producer/publisher separation over it, stage-2 admission/credential submission
and real request telemetry remain unimplemented as pipeline integration.
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
