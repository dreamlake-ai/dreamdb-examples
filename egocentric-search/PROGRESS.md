# Ego100K pilot progress — 2026-09-17

Issue: dreamlake-ai/dreamdb-core#400. Semantic search only; no lexical index.

## Main task: full-corpus ingest (2026-09-18)

User confirmed the **full Egocentric-100K corpus** as the goal, with cost and
phased budgets required BEFORE starting scale-up. See
[FULL-INGEST-BUDGET.md](FULL-INGEST-BUDGET.md). Authenticated metadata inventory:
29,966 TARs / 25,408,748,072,960 declared bytes, pinned revision; no video
download this turn. 58 original-only pilot clips remain the completed data
baseline, not a full-ingest checkpoint. No scale-up job has been submitted.
Performance experiments below are supporting work, not the primary completion
metric. [Stage 1 live status](STAGE1-INGEST.md): 1,000 new sources frozen,
12,408,995,840 B / 15 verified TARs; GPU ingest job 148022 started, not complete.
Stage 1 approved by the user's “继续”: up to 1,000 new clips, 32 GiB
source, one GPU / 12 GPU-hours. CPU catalogue job 148019 completed downloading
and hashing fixed non-pilot shards (at most 19,597,281,280 B for all 24 admitted
shards; stopped when 1,000 clips were frozen). This is source preparation, not
completed ingest. GPU writer targets stable Ref `ego100k-ingest-v1`, one clip
per checkpoint, private core bc77082. Real file-backed checkpoint preflight
148020 passes; disposable scratch removed by 148021. No scale-up beyond stage
1 and no new packing experiments. See ingest README for reproduction/state.

Latest optimization: [PACK-WRITE-RESULTS.md](PACK-WRITE-RESULTS.md). Opt-in
fragment packing plus selected adjacent-range coalescing: actual media payload
objects 44 → 2, same bytes; paired two-clip S3 means publication 1.137 → 0.991 s,
full read 1.050 → 0.318 s. First-range read 0.208 → 0.254 s: explicit tradeoff,
default unchanged. All byte/frame/range checks pass. Not total HTTP accounting,
not corpus-scale throughput; local commits only, no merge/release/CI this round.

Previous optimization: [LEAF-WRITE-RESULTS.md](LEAF-WRITE-RESULTS.md). Candidate
bc77082 overlaps eight independent fragment writes. Alternating two-real-clip
S3 runs all passed byte/frame/range checks; mean publication 4.349 → 1.130 s
(3.85x observed). This reduces latency, not request count; no merge/release yet.

Current measured summary: [RESULTS.md](RESULTS.md). Bounded cloud jobs are
complete; this is not closure of the full-scale/request-accounting work.

2026-09-18 batching follow-up: [BATCH-RESULTS.md](BATCH-RESULTS.md). Fixed 512
real vectors, single-writer batch 32/128/512: 26.77/9.89/5.73 seconds;
four-writer batch 128: 27.31 seconds, six conflicts. All four exactly reconciled.
The original-only full bounded GPU pilot also passed: 58 clips, 10,440 source-frame
vectors, zero skips, 58 range checks and eight semantic-query probes. Details:
[ORIGINAL-PILOT-RESULTS.md](ORIGINAL-PILOT-RESULTS.md). This supersedes the pending
full source-frame pilot status below. HTTP accounting remains open.

Latest continuation: [PATCHED-RESULTS.md](PATCHED-RESULTS.md). Original-only
VideoItem publication/range/decode passes on two real clips. Patched same-Ref
1/2 writers pass; 4 writers STOP on bounded CAS retry exhaustion, all 384
acknowledged records exactly reconciled, no unknown error. 8/16 not attempted.
This supersedes the "no patched remote rerun" status below, not its historical
measurements. Full source-frame embedding ingest and HTTP accounting remain open.

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

## Setup and remaining scope

- Slurm jobs 147820/147821 failed before Python/data operations: unavailable uv,
  then snap-specific ELF interpreter. Standalone official uv 0.12.6 archive
  checksum verified. Runtime job 147823 passed on RTX5090 with torch 2.9.1+cu128
  and torchvision 0.24.1+cu128. One srun probe (147822) failed step creation;
  sbatch is the working launch path. These are setup findings, not DB failures.
- Video-payload concurrency is now measured in 147838; HTTP counters remain pending.
  Application phase timing is not backend traffic measurement.

## Real pilot and first write case

147824 completed eight units, 58 clips and 10,440 vectors, no skips. The ingest
loop took 564.807 s: catalogue/acquisition 230.388, transcode 168.206,
decode/sample 25.086, encode 6.267, media append/commit 132.678. Calibration
took 1.466 s and vector publication 4.781 s. These phase timers are not HTTP
counters. Media readback passed for 728,331,965 original bytes and 1,316,517,665
preview bytes (39.116 s). Preview is larger here, not a storage saving.

Tokenization initially failed for a missing SentencePiece dependency after media
readback. Read-only 147825 resumed against unchanged tip
`dztstcp2xjy33x4jvclqsdd67oejdoa7rjm55cbjvzz3kxx64rrpe`: four semantic prompts,
two passes, ten results each; same anchors/order across passes. Not relevance proof.

147826 committed 512 real vectors in 16 batches (32/batch); 18.891 s worker time,
19.237 s including process startup. Its first readback incorrectly compared the
ordinary Python scan's RaBitQ reconstruction to original f32. This was an oracle
API-selection error, not established data corruption. The released source
explicitly decodes compressed bytes on ordinary scans, even with rerank enabled.

Reused existing `dump_exact_subset` compiled from **python-v0.0.14 / f0d6ac5**
(Slurm build 147827). Read-only reconciliation 147829 passed the original 512
committed vectors, anchors and digests; no data was rewritten. The workload now
uses scalar identity scans plus this exact-sidecar reader and still requires
every acknowledged vector, not the CLI's looser missing-subset threshold.

Optimized ingest 147828 passed with the SAME input selection and encoding
parameters, one-shard prefetch and 128 MiB logical media batches. Loop time was
365.632 s, versus 564.807 s: 1.545x in this observed pair. Phase times were
76.145 s catalogue wait, 168.201 transcode, 25.132 decode/sample, 5.425 encode,
88.534 media append, with 22 append calls instead of the baseline per-clip 58.
These are SDK calls, not HTTP requests. Comparison job 147831 checked all 10,440
anchors and vector payloads byte-for-byte; no differences. Both runs checked
original and preview digests. Network/cache equivalence was not controlled.

Write staircase 147830 ran after 147828, without overlapping timed ingest:

| Independent Ref writers | 1 | 2 | 4 | 8 | 16 |
| --- | --- | --- | --- | --- | --- |
| Wall seconds including startup | 20.620 | 10.638 | 5.740 | 3.465 | 3.083 |

All five cases acknowledged and exactly reconciled all 512 real vectors with
zero conflicts. Each fresh Dataset has a fresh Genesis/timeline; this is not
just replaying already-present immutable paths. Creation and readback are
outside these wall times. The workload is small, not sustained saturation.

Same-Ref one-writer passed (20.602 s). Same-Ref two-writer stopped: one writer
acknowledged 256, the other exhausted five explicit conflicts with zero
acknowledgements; all acknowledged records reconciled, readback issues empty.
The original short-backoff strategy was NOT advanced to 4/8/16 or relabelled
successful. A separate seconds-scale jitter strategy retains the five-attempt
cap; tune job 147834 measured single-writer batches 32/128/512 at
21.602 / 5.149 / 1.554 s, all PASS. Jitter two-writer passed; four-writer stopped
on unclassified S3 409 ConditionalRequestConflict, with all 384 acknowledged
records reconciled. No 8/16-writer escalation. Local core fix 8679b25 has 25
native connector tests passing; no patched package was used in these results.

Pipeline 147833 additionally overlaps one next preview with current encoding
and append. It passed at 406.778 s, not an improvement over 147828; comparison
147837 found all 10,440 anchor/vector records identical. Tune followed it.
The earlier queued pipeline 147832 was cancelled after its failed dependency,
before execution. No result is attributed to that job.

Read-only hit resolution 147835 passed. After tune stopped, its dependency was
explicitly changed to afterany; that released only independent read/media work,
not further same-Ref escalation. 147836 passed 320 retrieval queries (all
anchors/order equal to serial). 147838 passed 16 real clip pairs at all five
independent writer levels, with full media digest readback; details in RESULTS.

No saturation, recall or request-minimality claim is established.
No production Ref, old dataset, ACL, GC or public package was changed. No CI run.

## Resumable state

Local worktrees: `/Users/locatino/fortyfive/ddb-ego100k-ingest` and
`/Users/locatino/fortyfive/ddb-ego100k-bench` (local commits, not pushed).
Core fix: `/Users/locatino/fortyfive/ddb-400-cas`, local commit 8679b25,
awaiting formal qualification/review. Keep these small source worktrees until
handoff; unique unpublished work is not removed.
Selection and concise preflight outputs: `artifacts/ego100k-400/` in the local
fortyfive directory. Cluster task root: `/home/tom/ddb-ego100k-400`, now 33 MiB,
retains the original 147824 real vector inputs/calibration for reproduction,
selection, small scripts and reports. Duplicate optimized-run vectors were
removed after byte-for-byte comparison; the baseline remains.

After all benchmark jobs ended, Slurm cleanup 147840 completed with exit 0 on
node-099: twelve explicit task scratch directories (about 4.2 GiB) removed.
These held disposable model downloads and installed dependencies. Removed the
remote 904 MiB release-source/build tree and 135 MiB downloaded tool directory,
and the local core fix's 741 MiB target directory. Shared caches/services and
user-owned worktrees were not touched. These artifacts are reconstructible;
rerunning the helpers requires reinstalling the pinned standalone uv and
rebuilding dump_exact_subset at python-v0.0.14, as documented in README.

Job 147829 recorded `/tmp/ego100k-writes.xZTi1YFM`; it is absent on node-099 and
its completed Slurm placement has expired (accounting disabled). No claim of
cross-node deletion is made; no broad machine scan was performed.
Source originals/previews were retained at this checkpoint; the authorized
cleanup below supersedes this statement for obsolete media runs.
STS tokens exist only in submitting/job process environments, no credential
files. The three-hour sessions can remain valid until expiry after process exit.

## Authorized obsolete-media cleanup (2026-09-17)

Deleted from the isolated task bucket: 673 video-path objects totaling
6,937,625,720 bytes, plus 33 obsolete test Refs (706 keys in total).
The retired runs are pilots 147828/147833 and media groups
04883ed18589, 08f86c186977, 68e088121568, d7640592e590, dd6a38196858.
Before deletion, all current Ref manifests were read to check that the target
timelines were not shared with retained Ref bindings; exact target Ref bytes
were rechecked. S3 acknowledged every deletion without errors, subsequent
listings showed the 33 video prefixes empty and the target Refs absent.

Bucket versioning was disabled: these S3 deletions are not reversible.
The pinned HF input can be downloaded again. Baseline ego100k-pilot-147824
remains available for original/media and semantic regression, and all
ego100k-write-* Refs remain for vector/concurrency tests and CAS reproduction.
No global index/compressor, vector data, Manifest history or other dataset was
deleted; residual unreferenced metadata is intentionally left without GC.
Thus this is obsolete-media cleanup, not an empty-bucket reset.

The exact key/Ref inventory and deletion result are retained locally in
`/Users/locatino/fortyfive/artifacts/ego100k-400/media-cleanup.json`.
The next ingest uses a fresh Ref and the original-only segmented contract in
PLAN.md; no new ingest was launched as part of this cleanup.

## Blocking fixes (local only)

See [FIXES.md](FIXES.md): S3 409 classification passes 25 HTTP boundary tests;
base-field multi-append merge now passes the original ingest integration case
and exact scalar readback; Python VideoItem schema/publication is implemented
and its installed-wheel selection passes (389 passed, 1 skipped).
These supersede the local implementation gaps, not the earlier S3 measurements.
No patched remote rerun, formal bound testbox verdict, CI or package release yet.

Follow-up: the three fixes were combined in core PR #401 and merged into main
as `0ec901f0ada7050a05ec689b137c1e87e6741139`, after all 14 PR checks passed.
This supersedes the preceding local-only/CI-pending status, not the remote-run
or package-release limitations. Issue #400 remains open. The completed core
worktrees ddb-400-video, ddb-400-merge and ddb-400-cas can now be removed;
unfinished ingest/example worktrees remain for segmented-pilot integration.
