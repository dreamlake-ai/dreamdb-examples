# Ego100K pilot progress — 2026-09-17

Issue: dreamlake-ai/dreamdb-core#400. Semantic search only; no lexical index.

## What is established

- The new private task bucket exists, with public access blocked. Source/model
  revisions and the eight-shard selection are pinned in SPEC/selection inputs.
- Ingest adapter and original+preview public append path implemented in separate
  `dreamlake-ingest` worktree. Released SDK under test: dreamdb 0.0.14.
- Native local preflight: 244 unit tests pass, one skips. Real generated-video
  append/reopen checks both original bytes and generated preview SHA256. This
  is not an Ego100K performance or scale result.
- Actual two-handle FsConnector check on 0.0.14: first append succeeded, stale
  second append raised RuntimeError `publish conflict on ref ...: it advanced
  concurrently; re-open and retry`; fresh read contained only the first anchor.
  This validates the explicit conflict classification used in `write_stress.py`,
  not S3 atomicity or multi-process throughput.
- Existing branch merge integration rejected the second branch after merging
  the first (different exact parents). Consolidation remains unresolved.

## Running / pending

- Slurm jobs 147820/147821 failed before Python/data operations: unavailable uv,
  then snap-specific ELF interpreter. Standalone official uv 0.12.6 archive
  checksum verified. Runtime job 147823 passed on RTX5090 with torch 2.9.1+cu128
  and torchvision 0.24.1+cu128. One srun probe (147822) failed step creation;
  sbatch is the working launch path. These are setup findings, not DB failures.
- Bounded real pilot resubmitted as **147824**. Completion not established.
- `write_stress.py` implemented, not run with real data yet. First fixed workload
  is 512 vectors / 32 per commit, each explicit level 1/2/4/8/16; no automatic
  escalation. Independent-Ref and same-Ref results are separate. Fresh readers
  compare exact vectors, digests and anchors; ambiguous outcomes stop.
- Video-payload concurrency and connector-level HTTP counters are still pending.
  Application phase timing is not backend traffic measurement.

No throughput, saturation, recall or request-minimality claim is established.
No production Ref, old dataset, ACL, GC or public package was changed. No CI run.

## Resumable state

Local worktrees: `/Users/locatino/fortyfive/ddb-ego100k-ingest` and
`/Users/locatino/fortyfive/ddb-ego100k-bench` (local commits, not pushed).
Selection and concise preflight outputs: `artifacts/ego100k-400/` in the local
fortyfive directory. Cluster task root: `/home/tom/ddb-ego100k-400`; job output
and `runs/<job>/scratch-path.txt` identify task-only artifacts. Keep while the
pilot is unfinished; clean completed scratch after collecting the result.
Source originals/previews in the S3 task bucket are intentionally retained.
STS tokens exist only in submitting/job process environments, no credential
files. The three-hour sessions can remain valid until expiry after process exit.
