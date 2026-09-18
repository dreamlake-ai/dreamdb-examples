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

Status at this record: GPU runtime initialized, ingestion running, **not PASS**.
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
