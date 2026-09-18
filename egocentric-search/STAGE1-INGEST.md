# Full-corpus ingest, stage 1 — 2026-09-18

User approved continuing the proposed first stage: up to 1,000 new clips,
32 GiB source transfer, one GPU, 12 GPU-hours total. $10 requests/egress is a
review budget, not a hard AWS billing cutoff. No later-stage authorization.

## Frozen inputs (actually acquired)

CPU Slurm 148019: exit 0, 10m16s, no GPU, no S3 writes/STS issuance.
15 source TARs downloaded, full-size/SHA256 checks passed; **12,408,995,840 B**.
24 candidates total 19,597,281,280 B; acquisition stopped at 1,000 clips,
so nine candidate shards were not downloaded. All eight pilot source shards
were excluded from this batch to avoid repeating the 58 measured clips; their
unprocessed members remain outstanding in the corpus inventory.

- 1,000 admitted clips, 179,646.574 declared video seconds (~49.9 hours).
- Largest admitted MP4: 15,267,540 B.
- Source revision: `fae604b751b25337d6fd8c4c53e595910c28f68f`.
- Frozen catalogue SHA256:
  `8dfc8d6beb89a035444d72ef1e0130fa0652a5a14d7c5e7882e67eb0222973ee`.
- Location: `/home/tom/ddb-ego100k-400/stage1/catalogue.json`.
- Complete acquisition ledger: same directory, `acquisition.json`; archives in
  `archives/` retained for the active GPU job and restart, not disposable yet.

Full corpus stable identity is `(source revision, shard path, member path)`.
Stage 1 assigns sequential clip ordinals and one-hour anchor windows, frozen in
the catalogue. Future batches must extend this mapping, never reorder it.
Unsupported size/duration/codec causes explicit failure; no silent pilot
sampling filters. Any unprocessed or unsupported clips remain outstanding.

## Writer and minimal checks

Ingest source commits b366742, f40ec22, 2ea9ef2. Uses existing `dlingest.run`
with one clip per unit, source-frame embeddings, original stream-copy media,
no preview, no lexical stage. Exact vectors/rerank remain enabled.

Private core bc770820191d3ca85eef9441572e0cd3fd04f90d; wheel SHA256
`b4147916e795b0e48d2a311f02949167b961846036d534b5e3a09b69ea5271ca`.
Uses qualified eight-way leaf writes; optional packing is NOT enabled.

Ref: `ego100k-ingest-v1` in the existing private task bucket. It is not a new
benchmark Ref on each launch. Exact acknowledged tip/config/catalogue is bound
to `stage1/work/checkpoint.json`, protected by a single-writer lock. Confirmed
media signatures skip repeat publication; ambiguous pending operation plus
changed remote tip stops for reconciliation. Unknown create does not fall back
to opening a possibly unrelated Ref. Fixed vector chunks have commit receipts.

Actual public-boundary check: CPU job 148020, private wheel, real generated
H.265 → publish → reopen → resume, unchanged tip and correct readback; a
successful but unacknowledged publication causes a stop rather than blind retry.
1 pass in 0.55s. Local unit selection: 246 pass, 1 skipped, 9 deselected;
includes source identity / unsupported-duration admission. No formal testbox
Evidence, CI, new framework or claimed full-corpus proof.

One local plan invocation initially lacked PYTHONPATH; corrected the invocation,
not the source data. No source download occurred in that failed invocation.

## Execution

GPU Slurm **148022** started on bos14-node-099 (RTX5090, 32,607 MiB VRAM),
8 CPUs / 32 GiB requested, **2h job time limit**, first 2h reservation out of
the 12 GPU-hour stage ceiling. Submission ledger is `gpu-admissions.json`;
each attempt conservatively consumes its full 2h allowance (at most six), even
if it fails early. No automatic resubmission. Temporary STS expiry reported
`2026-09-18T06:28:07+00:00`; process exit does not revoke that session.

Latest status: first **176/1,000** clips have confirmed media + local vectors.
Initial job 148022 stopped on S3 HTTP 500 at clip 163; resumed job **148027**
has passed that clip and is running. Vector layer not yet published, **not PASS**.
Source-prepared clips are not media-committed clips, and media-committed clips
are not published embeddings. `MEDIA_ENCODED` records media + local vectors;
`VECTORS_COMMITTED` records acknowledged vector layer writes; final result
requires identity readback plus bounded playback/semantic checks.

Output: `/home/tom/ddb-ego100k-400/stage1/work/result.json` only after checks.
Log: `/home/tom/ddb-ego100k-400/logs/stage1-ingest-148022.log`.
Postconditions: all admitted clip IDs/anchors read back; local unique vector
count and acknowledged commits; three media range samples and four semantic
queries. This is NOT a full remote exact-vector census or all-video readback.
Growing index/Track/history costs and same-Ref contention are later-stage gates.

## Cleanup

Preflight job finished; exact scratch `/tmp/ego100k-stage1-test.nPdQTVCt` on
node-121 removed by Slurm 148021 (`CLEANED`, no S3 deletion). Active stage1
archives, vector/checkpoint state, GPU scratch, and unpublished local source
worktrees must remain until completion/reconciliation; no shared caches touched.

## Live performance observation (job still running)

At job elapsed 8m55s: 145 media+local-vector units complete, no ingest failure
observed. Earlier log snapshot ending at clip 107 gives these rolling windows
(log timestamps have one-second resolution):

| Completed-clip window | Seconds per clip | Clips per minute |
|---|---:|---:|
| 20 | 3.421 | 17.538 |
| 50 | 3.449 | 17.396 |
| 100 | 3.455 | 17.368 |

This excludes the earlier HF acquisition and does not include still-pending IVF
calibration/vector publication/readback. It is not full-corpus throughput or a
completion ETA. No early throughput decay is evident in these windows.

Read-only sampling used short `srun --jobid=148022 --overlap` steps within the
existing allocation, not a second ingest or competing GPU workload:

- Twenty 1s GPU readings at 23:34:50–23:35:09 (node clock) report 0% utilization,
  2,298 MiB device memory and roughly 87–110 W. This does not prove no CUDA work;
  the configured model and input tensors explicitly use CUDA. Short-burst vs
  device counter behavior is unresolved, and no instrumentation experiment was
  added to disambiguate it while the main task runs.
- Twenty 1s checkpoint samples: 8 media-publication pending, 7 metadata-append
  pending, 5 between commits; confirmed media increased 126→131. Occupancy
  sampling, NOT exact phase-duration attribution or measured HTTP request count.
- Main Python process: VmRSS 1,604,324 KiB (~1.53 GiB), VmHWM 1,710,868 KiB
  (~1.63 GiB), 32 threads. Excludes ffmpeg/other children and is not job-wide RSS.
- `sstat` returned unusable CPU/empty RSS values, so they are not reported as
  utilization. The log's two initial “Failed” matches are pip hardlink-fallback
  warnings, not failed ingest units.

Interpretation: the source loop serializes media publication, decode/encode and
metadata publication; sampled commit occupancy suggests pipeline overlap and
publication batching deserve priority over simply adding GPUs. It does not
prove S3 throttling, a GPU fault, or the exact savings of a prospective change.
Do not restart this job or rerun completed clips for a comparison. Its existing
`timings` dictionary records actual aggregate remux/media/decode/encode/metadata
times in the final result. Reassess with those measurements and later rolling
windows before authorizing stage 2. Optional packing remains off.

## Actual interruption and reconciled continuation

148022 stopped at the 163rd clip: a media leaf PUT returned S3 HTTP 500
`InternalError`, request ID `FB6Q4ZWK49NW70D7`. The last completed unit is
162. This is a failed attempt, not an unchanged-state wait or inferred throttling.
Its final aggregate phase timings were only in memory and were lost; the earlier
rolling-window and occupancy observations remain, but cannot fill that gap.

Before resubmission, read the actual S3 Ref (33 bytes) and compared it with the
durable checkpoint. Both were
`dzsgcnlsxu4pghrio6kduodgw2fszpaw7gur7ba7hn3mkhyhctxg4`.
There were 162 media receipts and 162 local vector shards; pending operation
type was media. No old Ref overwrite, failed-unit success marker, or manual tip
substitution. The existing resume guard independently checks the tip again.

Resume **148027** with fresh scoped STS (expires 2026-09-18T07:46:07Z), same
qualified core/wheel/input identity. Second 2h reservation: 4/12 GPU-hours
conservatively reserved, not 4h actually consumed. Log confirms resume at clip
163, then progress beyond it; previous 162 units skipped without media replay
or source redownload. Original source archives remain intact.

Ingest commit a86b40f adds per-attempt telemetry every 25 clip ordinals and at
unit failure, plus calibration and vector-publication attempt timings. It does
not change storage contents, the replay guard, or retry limits. Local unit suite
246 pass / 1 skipped / 9 deselected. No new CI or validation framework.

First persisted sample: total 175 media units, **13 new units in this attempt**:

| Measured operation | Cumulative seconds (13 new clips) |
|---|---:|
| Media publication | 18.349 |
| Metadata append/commit | 20.511 |
| Decode/sample | 13.304 |
| GPU encoder call (including transfers/normalization) | 1.336 |
| Stream-copy remux | 0.329 |

Job elapsed was 71.533s and includes setup/archive checks outside these timers.
These serial call measurements directly support prioritizing publication and
decode/encode overlap over adding GPUs. They are not HTTP wire timings, full
attempt totals, or an estimate for unmeasured remaining clips. A single 500
interrupting the batch is also a real reliability cost: this turn resumes after
checking state; no new automatic retry policy is smuggled into the workload.

After clip 163 succeeded in the new job, old node-099 scratch
`/tmp/ego100k-stage1-gpu.x3RTXcnE` was removed through a short Slurm overlap step.
Failure log, source TARs, 162 old vector shards and checkpoint remain; no S3
objects removed. Active scratch is `/tmp/ego100k-stage1-gpu.aaI9nBRd` and must
remain while 148027 runs. Partial/unreferenced remote objects from the failed
publication were not deleted or GCed.

## Resume 148027: deterministic lineage-capacity stop

The resumed attempt stopped during clip 233's metadata append:
`lineage container is 1049865 bytes, over the 1048576 limit`.
Checkpoint inspection: 233 acknowledged media receipts, 232 local vector NPZ
files, pending `metadata`, checkpoint tip
`dyolslcr64fknyjkbuhtel2ugzfuzcztmazumnbiohnbxnt7etvdo`.
This is the checkpoint value, not a fresh independent remote-tip verification.
No stage result/PASS or vector-index publication is claimed.

Persisted attempt telemetry: elapsed 331.921 s; media publication 106.937 s
(71 commits); metadata append 120.317 s (70 successful commits; timing also
includes the failed call); decode/sample 75.742 s; encoder 6.596 s; remux
1.961 s. Counts/times cover this attempt only. This failure is unrelated to
the preceding attempt's HTTP 500; unchanged resubmission cannot fix it.

Source diagnosis: append.rs replaces each changed active Track with
DerivedFrom(the published base). Builder closure retains that ancestor chain.
spec/0002 section 7.2.3 explicitly caps the canonical lineage-v1 container at
1 MiB and forbids silent paging/truncation. Compact also derives its new Track
from the replaced version, so ordinary compaction does not reset this growth.
Increasing metadata batches may delay the cap, not remove the full-corpus
scaling limit. No cap change, ancestry removal, root replacement, or dataset
partitioning has been performed or silently authorized by this diagnosis.

No replacement GPU job submitted. Retain checkpoint, vectors, TARs and node
scratch `/tmp/ego100k-stage1-gpu.aaI9nBRd` for recovery of the interrupted unit.
Resolving this blocker requires choosing a bounded-history/checkpoint contract
or extending lineage storage; it is not another throughput parameter change.

## Current-SDK resume after #402/#404 (2026-09-18)

The earlier stop is now addressed by the explicit checkpoint APIs, not a larger
container limit. Latest merged main at qualification was
`743f72a3d32679bc6a4366ca55689c1fc62e6548` (#402, #404 and #397 included).
Private core `cd71b1a47ffff63ba0505d360d863ec003b07093` adds ONLY the already
measured eight-way independent media-leaf writes from `bc77082` to that main.
Main still writes those leaves serially; silently swapping to unmodified main
would drop that prior performance change. No optional fragment packing enabled.

Slurm CPU build **148123** produced the pinned wheel (still labelled 0.0.14):
SHA256 `0f55a836c1d639cd44797d56cfe1560e1971fec2cd946f3bed5011ffa4296097`.
Package version alone is not provenance. The launcher checks that exact hash,
installs into task-private dependencies and verifies DreamDB imports from there;
it no longer installs an old registry SDK first. Source/model/catalogue pins
are unchanged. 393 Python tests passed / 1 skipped; native media writer
preflight 8 passed / 1 ignored. Adapter units 246 passed / 1 skipped / 11
deselected. A local invocation initially used nonexistent `--extra dev`;
corrected to the existing `--group dev` without changing tests or dependencies.

CPU preflight **148125**, installed same wheel: 3 public file-backed tests PASS
(0.34 s), including real H.265 publication, receipt-preserving SDK upgrade,
base checkpoint, corrected-RaBitQ IVF layer + exact sidecars, indexed checkpoint,
lost-local-receipt recovery, subsequent append and query/media readback. These
are direct integration preflights, not a new formal testbox verdict.

Before resume, one independent S3 GET returned the 33-byte Ref matching the
saved tip `dyolslcr64fknyjkbuhtel2ugzfuzcztmazumnbiohnbxnt7etvdo`.
Adapter **b0a3336** journals the qualified old→new SDK binding only after actual
tip reconciliation. It cannot change catalogue/model/backend/Ref identity or
replace the saved tip by guesswork. Base checkpoints run at media-unit boundaries;
indexed checkpoints can run at vector-chunk boundaries after layer creation.
Saved plans precede remote publication; unknown ordinary commit outcomes still
stop, with no new automatic retry policy.

GPU resume **148126**, bos14-node-121 / RTX5090, is RUNNING. Third 2h reservation:
**6/12 GPU-hours conservatively reserved**, not 6h consumed. Same 1,000 clips,
no new downloads, no stage-2 expansion. STS expires `2026-09-18T12:18:21Z`;
process exit does not revoke the session. The launcher verified the new wheel
and logged its isolated import path. The first checkpoint applied as:

- source: `dyolslcr64fknyjkbuhtel2ugzfuzcztmazumnbiohnbxnt7etvdo`
- new root: `dzc5ehjflpqk34xub27kaxpgapct5xd4jj2wnjzq26hu63ykctphu`
- archive tag: `ego100k-dyolslcr64fknyjkbuhtel2ugzfuzcztmazumnbiohnbxnt7etvdo`

233 media receipts / 232 local vector shards were retained at this boundary.
Vector layer publication and final stage readback are still pending. Log:
`/home/tom/ddb-ego100k-400/logs/stage1-ingest-148126.log`.

Cleanup: the completed new SDK build's 1.9 GiB target, 132 MiB build environment
and pytest scratch were removed after saving the wheel and exact-read CLI.
CPU-test node scratch cleanup initially used an incompatible inherited GRES;
the step was corrected to `--gres=none` (not an ingest failure). Active GPU
scratch, source TARs, vectors, journal, wheel and unpublished source worktrees
remain necessary for this running job. No S3 deletion or GC.

Later observation in 148126: **278 completed media/local-vector units**, 279
media receipts (one next unit between media and vector completion). The failed
233rd unit has completed; the previous 232 local vector artifacts were reused,
not regenerated. At the durable 275-unit snapshot, attempt elapsed 269.685 s:
media calls 43.173 s, metadata appends 42.910 s, decode 44.427 s, encoder 5.250 s,
remux 1.394 s. Both call counters are 43; the media counter includes the receipt
skip for unit 233, so it is NOT 43 new remote publications. No HTTP request count,
isolated speedup or final throughput is inferred. Published vector offset is
still zero; calibration, vector publication and final acceptance remain pending.
