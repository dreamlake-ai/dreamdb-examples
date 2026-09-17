# Implementation plan and current facts

Issue -> workload spec -> implementation plan -> bounded execution, per #400.

## Patched bounded continuation (2026-09-17)

Core is pinned to main `0df51db7b2d2ae51ae219cb53a2936e91926e98e`
(#401 plus #399/#396). Build a private wheel and the existing exact-reader CLI
on Slurm; do not publish packages or reuse the old package label as provenance.
First check two retained real clips from pinned baseline `dztstcp2…` in a fresh
`ego100k-original-smoke-<job>` Ref: stream-copy all source streams, per-item
init, publish/reopen, full fragment hashes and encoded-stream/decoded-frame
comparison, then a decodable interior range. This is not browser playback.
No HF re-download, preview, codec conversion or full-corpus ingest in this step.

Then reuse the original 512 actual vectors and calibration for the same-Ref
1/2/4/8/16 staircase, batch 32, existing five-attempt jitter policy. Reconcile
all acknowledged anchors/digests/exact vectors through a fresh reader. Stop on
the first failed level; do not silently increase retries to make 16 writers pass.
Run sequentially, at most 8 CPUs / 16 GiB / 30 minutes, no GPU allocation;
the separate build has a 40-minute limit. No production Ref or old object changes.
API phase timings remain distinct from unmeasured wire-level request counts.

The opt-in `video-item-original` adapter uses source frames and a new embed spec;
preview-derived vectors are not an equivalence baseline. Its full bounded GPU
pilot remains subsequent work, after the small real media check passes.

## Superseding media decision (2026-09-17)

The next run must use a fresh Ref: source HEVC video only, stream-copy
segmentation without re-encoding, no preview or compatibility transcode.
Embedding frames must be decoded from the original. The whole-clip + preview
measurements below remain historical results, not the new ingestion contract.
Use per-item decoder initialization and fragment indexes (VideoItem); the old
flat CMAF Track's shared-init constraint must not be bypassed for heterogeneous
originals. Python 0.0.14 exposes VideoItem reads but lacks its schema/write
bindings; resolve this integration gap before launching another pilot.

Primary claim for the next media check: independently initialized real source
clips can be published as no-transcode fragments, fetched for a time window and
decoded, with encoded content retained. A bounded real publish/range-read/decode
check is sufficient; container-byte identity is not required after remuxing.
Do not infer browser playback from successful storage or FFmpeg decoding.
The existing pilot resource/selection bounds remain unchanged.

The user authorized removing obsolete uploaded originals and previews. Keep
baseline pilot 147824 for original-media/semantic regression and all vector
write-test Refs (including CAS failure reproduction); retire duplicate pilots
147828/147833 and the five completed media-throughput groups. Do not run GC,
delete global shared indexes, or apply this permission to other datasets.

Reuse decision: [INGEST-REUSE.md](INGEST-REUSE.md). Data preparation belongs in
dreamlake-ingest's existing phase library and a new ego100k adapter. This example
retains the experiment contract, query/write workload and results, not a second
ingest engine. Required SDK/media/source adaptations precede runtime claims.

1. **Access and resources**: HF CLI login confirmed; pinned gated intrinsics GET
   returned 200, 291 bytes, JSON decoded; no video downloaded. SHA256
   `fa58346374c429a9f47e60e1e4355a1b7849005f4ee95b7a2b138017624b2315`.
   Root metadata lists 238 factory directories. Slurm controller bos14-ctrl is
   reachable as tom; use sbatch, never controller GPU/ingestion workloads.
2. **S3**: newly created task bucket
   `s3://dreamdb-ego100k-bench-747143892217-20260917`, account 747143892217,
   us-east-1 (configured default, not a measured proximity claim). Ownership
   BucketOwnerEnforced, all four public access blocks, SSE-S3 AES256 and task
   tags. Authentication for workers must be short-lived and scoped to this
   bucket; never copy the user's long-lived AWS key. The bounded pilots now
   retain real originals/previews and vectors there; see PROGRESS.md.
3. **Metadata selection**: deterministic spread across factories, seeded worker
   and shard selection; known sizes, <=8 GiB. Retain the manifest with the run.
   Sampling does not claim population representativeness or labeled relevance.
4. **Pilot**: inspect existing node runtime/model cache without modifying shared
   environments. Prepare task environment and least-privilege credentials; submit
   one bounded Slurm job. Decode original temporary video, produce preview and
   image embeddings, record cost; preserve exact original MP4 and preview in S3
   with their digests/linkage. Delete processed local original scratch only after
   upload confirmation. Keep remote originals for later experiments. Train a
   sufficiently sampled IVF index (do not mechanically copy ego10k parameters).
5. **Public write and read path**: pin released DreamDB package/source; implement
   isolated ingest with explicit identities and reopen/query/readback. Measure
   S3 operations at the real connector/HTTP boundary, not calls to an application
   wrapper. Keep encoder timing outside storage timing. Do not write an emulator
   of S3/CAS. Identify any public SDK capability gap before working around it.
6. **Concurrency**: implement independent-Ref and same-Ref workloads from SPEC;
   staircase after sequential success. Max 16 writers initially. Stop/rerun rules,
   retry caps and request budgets are fixed before launch from pilot measurements.
7. **Scale decision**: use measured throughput/storage to propose 1M then 10M
   actual vectors; no automatic larger budget. At 1 fps the complete corpus is
   about 361M frames, not 100K vectors.
8. **Report/cleanup**: compact reproducible results, failed runs and limitations;
   no private raw logs or raw media in Git. Clean task scratch/builds once done,
   preserve pending work. Retain S3 originals and previews for future experiments;
   remote data deletion requires separate direction, not automatic task cleanup.

## Runtime preparation (2026-09-17)

The ingest worktree now has an opt-in whole-clip original/preview path and the
bounded ego100k adapter. Local native preflight: 244 unit tests pass, one skips;
a real generated-video append/reopen test passes with dreamdb 0.0.14 and exact
original-byte comparison. This is storage wiring evidence, not real-data scale.

Existing integration also exposed a merge incompatibility: the first branch
merged, the second was rejected because layers named different exact parents.
Do not retry the entire merge, discard branch data, or conflate branch-local
commit success with consolidated visibility. Independent-Ref and same-Ref
tests remain separate; consolidation is a separately reported result.

Only semantic search is in scope. No BM25 build or lexical-query tests.
The pilot records acquisition/catalogue, transcode, sample/decode, encoder and
SDK append/commit time separately. These are application phase times, NOT HTTP
request counts or backend wire throughput. Real connector counters remain to
be implemented before request-count claims.

High-concurrency testing is a DreamDB product test, not just ingest scheduling:
1/2/4/8/16 independent writer processes; fresh isolated Refs for every case;
same-Ref CAS conflict classification/reconciliation is a distinct workload.
Use actual precomputed pilot data, stable disjoint anchors and fresh-reader
verification of acknowledged contents. Stop escalation on missing/changed
acknowledged data or unclassified commit outcomes. Fix product defects at their
source, not by relaxing the readback assertion. Measured results and stopped
cases are recorded in PROGRESS.md; they do not establish full-corpus scale.
