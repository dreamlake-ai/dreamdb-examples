# Implementation plan and current facts

Issue -> workload spec -> implementation plan -> bounded execution, per #400.

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
