# Full Egocentric-100K ingest: proposed budget and execution gates

2026-09-18. User objective is now **the full corpus**, not another performance
experiment. User explicitly requested a total-cost and phased-budget proposal
BEFORE scale-up. The old 8 GiB / 64-clip pilot authority is not permission to
start full ingest. This document proposes, but does not approve, larger jobs.

## Fixed scope and current position

- Original source codec, stream-copy fragments and per-item init, no preview,
  no lexical index. Remuxing preserves encoded media, not original MP4 container
  byte identity. Keep source SHA256 and source member identity.
- Semantic embeddings: proposed continuation of pinned SigLIP, original frames,
  1 fps, dim 768, preserving exact vectors/rerank as in the successful pilot.
- Existing complete original-only pilot: 58 clips / 10,440 vectors, Ref
  `ego100k-original-148008`, manifest
  `d3zjkyj2hwkzt5nosibogh5x6wxpujgw3x32vuqb4gaashzpatka4`.
  This is not a partially completed full-corpus Ref. Its stable identities and
  artifacts must be reconciled for reuse, not counted twice or rerun for progress.
- Latest packing experiments do not add corpus coverage. Packing is opt-in;
  neither those patches nor another optimization experiment is a prerequisite
  to the planning phase. Select and freeze a qualified SDK before real scale-up.

## Source inventory — actual metadata, no video transfer

Repository `builddotai/Egocentric-100K`, revision
`fae604b751b25337d6fd8c4c53e595910c28f68f`.
Authenticated recursive HF tree enumeration completed:

| Item | Observed |
|---|---:|
| TAR shards | 29,966 |
| Sum of declared TAR bytes | 25,408,748,072,960 |
| Decimal TB / binary TiB | 25.409 / 23.109 |
| Factory directories represented | 238 |
| Worker directories represented | 14,228 |
| Smallest / largest TAR | 7,280,640 / 2,523,822,080 B |
| Other files | 14,231 |
| Video bytes downloaded this turn | 0 |

TAR size includes archive overhead and annotations, not measured remux output.
Other files were counted but not classified; a full clip inventory is NOT
established by a TAR tree. Before data execution, classify non-TAR paths for
additional media and enumerate each admitted TAR's members without the pilot's
silent oversize/duration filters. Clip totals come from the pinned card, not
this tree: **2,010,759 clips / 100,405 hours / 24.79 TB**. The actual TAR total
supersedes the card's storage figure for source-transfer planning.

Frozen inventory: local `artifacts/ego100k-400/full-shard-inventory.json`
(9.7 MiB, retained as the unfinished task's input, not checked into Git).
SHA256 `566c9765953d98005c169b973600e9741ecc1bc21ec223f489b6f4e249724e28`.
Reproduce with ingest `spaces/ego100k/inventory.py --output <new-file>`; no
video download, S3 mutation, or credentials in its output.

## Cost model (USD, us-east-1 S3 Standard)

Official price-list snapshots queried 2026-09-18:

- [S3 regional price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json),
  version `20260917231010`: first 50 TiB $0.023 per billing GB-month;
  PUT/COPY/POST/LIST $0.005 per 1,000; GET $0.0004 per 1,000.
- [Data transfer regional price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDataTransfer/current/us-east-1/index.json),
  version `20260916132208`: internet outbound first 10 TiB $0.09/GB,
  next 40 TiB $0.085/GB, before considering account-wide free allowance.
- [S3 pricing](https://aws.amazon.com/s3/pricing/): ingress to S3 is free;
  that does not mean HF service or cluster ISP traffic has no cost.

Use bytes / 2^30 for these AWS billing GB estimates; TB/TiB are explicit above.
Exclude tax, credits, account-specific tier aggregation, discounts, acceleration,
NAT, HF paid services, and cluster/ISP tariffs. No such services are enabled by
this plan. The zero-cost S3-to-AWS transfer SKU is NOT internet egress pricing.

| Component | Working estimate / limitation |
|---|---|
| Media | TAR-sized allowance: 23.109 TiB, about **$544/month**. Actual fragment output unknown globally. |
| Exact vector payload | 100,405h × 3600 × 1 fps × 768 × 4 = **1,110,398,976,000 B**, about **$24/month**. Duration-derived estimate, not exact sampled-frame count. |
| Compressed records | Illustrative 108 B/record gives 39.04 decimal GB, about $0.84/month; verify actual new format and headers rather than treating it as a complete index. |
| Track/index/proofs/history | Not yet measured at scale. Propose **30 TiB total physical bucket occupancy** review ceiling (about **$707/month**), not a proven size upper bound. |
| Requests | Each 10M PUT-class requests costs $50; each 10M GET costs $4. Full request counts including retries and metadata are unknown. |
| Verification/download | Budget sparse checks, not full S3 replay. Downloading the TAR-sized footprint back to bos14 once would cost roughly **$2,063** before account allowances. |

**Proposed AWS envelope:** review ceiling **$1,500 one-time request + egress
spend**, separately from storage up to **$707 per full month**. Thus a first
full-month envelope is about **$2,207 plus cluster/ISP/tax**, NOT a forecast or
a hard billing guarantee. Storage is prorated during fill; subsequent months
continue charging. No-GC history and failed-run objects count toward occupancy.
If the measured slope threatens either ceiling, stop scheduling and revise the
plan; do not delete required data or silently lower quality to fit the number.
AWS billing/usage reports lag and budget alerts are not spending kill switches.

GPU tariff is not known: use allocated GPU hours × the owner's actual rate R.
CPU, shared storage and network costs are additional if not included in R.
For illustration only, an 8,000 GPU-hour envelope costs $8,000 at R=$1/h or
$16,000 at R=$2/h. These are not advertised cluster prices.

## Time — reference arithmetic, not promised ETA

Measured 58-clip original-only job: 503 allocated seconds on one RTX5090,
8 CPUs / 32 GiB. Simple clip-count scaling gives **4,844 GPU-allocation hours**.
This extrapolation includes GPU idle during network/publication; it does NOT
mean the encoder needs 4,844 GPU-hours. Encoder timing alone extrapolates to
about 51.8 hours; decode to 597 hours on that allocation. These are overlapping
stage measurements and must not be added as independent job durations.

At perfect scaling, 4,844 allocation-hours is ~25 days on 8 GPUs or ~13 days
on 16. Neither perfect scaling nor stable request/metadata growth is established.
Propose a cumulative **8,000 GPU-hour ceiling** across all stages, not an ETA.
25.409 TB at sustained 1 Gbit/s is ~56.5 hours one-way wire time, 10 Gbit/s
~5.65 hours: neither is measured bos14 throughput or an end-to-end lower bound
when input/output overlap. Do not promise these download rates.

Observed now: 42 idle RTX5090 nodes and 51 idle rtxpro6000 nodes in the two
partitions, subject to other users and scheduling. Hardware availability is not
permission to occupy it. Shared /home has ~1.9 TiB free: **never stage the corpus
there**. Stream bounded shards through node-local scratch; retain only restart
state/calibration data on shared storage with an explicit separate bound.

## Proposed stage gates (each row is an authorization boundary)

Counts are cumulative coverage targets; per-stage transfer/compute limits are
incremental except the final explicit cumulative ceilings. Stop at whichever
limit occurs first, report partial progress, never hide failures as completion.

| Stage | Coverage target | Allocation cap | Input / scratch cap | Incremental request+egress budget |
|---|---|---|---|---:|
| 0, preparation | no new media | metadata/code only | frozen inventory and durable ledger | no new data job |
| 1, production path | 1,000 unique clips | 1 GPU, 8CPU/32GiB, 12 GPU-hours | 32 GiB HF transfer, 64 GiB local scratch | $10 |
| 2, scale check | 10,000 unique clips | at most 4 GPUs, 100 GPU-hours | 256 GiB HF transfer, 64 GiB scratch/worker | $40 |
| 3, sustained batches | 100,000 unique clips | at most 8 GPUs, 800 GPU-hours | 2 TiB HF transfer, 64 GiB scratch/worker | $150 |
| 4, full completion | full frozen corpus, no unresolved clips | at most 16 GPUs; 8,000 GPU-hours cumulative | 30 TiB cumulative HF transfer, 64 GiB scratch/worker | $1,300 (total $1,500) |

Storage charged separately; 30 TiB total physical S3 review ceiling. Shared
checkpoint/vector staging proposal: 256 GiB fleet-wide, with completed chunks
published/verified before eviction. Local scratch free-space checks apply on
each selected worker. Each job remains shorter than its temporary credential
lifetime; fresh scoped credentials for later batches, no indefinite secret files.
Caps are enforced in admission/scheduling before larger work, where measurable;
the monetary numbers are review budgets, not implemented billing guards today.

Stage 1 must report actual complete clips, source/stored bytes, vectors, allocated
time, request/retry counts and retained metadata growth. Stage 2 must show
checkpoint resume and measured scaling, not just four successful jobs. Later
rows require an updated cost forecast based on those results before approval.

## Required implementation, not another performance side project

1. Stable source identity `(revision, shard path, member path)` and deterministic
   anchors/item keys. Remove sampling for admitted work; never silently exclude
   >256 MiB clips, long clips or codec variants. List unsupported inputs as
   unresolved with reasons; do not claim full ingest while any remain.
2. Persistent corpus ledger: source inventoried → media committed → embeddings
   committed → checked. Bind entries to exact Ref/tip and config/model revision.
   Reconcile uncertain publication against remote state before retry. Current
   pilot's new-Ref-every-run and unit-only markers are insufficient for full
   ingest; do not simply lift the 64-clip guard.
3. Bounded parallel download/decode/GPU producers and controlled publication to
   the intended corpus. No independent permanent Ref per job masquerading as
   one searchable dataset. Resolve shared index/calibration and exact parent
   version consistency before multiworker publication; global training uses a
   bounded representative reservoir, not loading ~1.11 TB f32 into 32 GiB RAM.
   Any planned index rebuilds must enter the budget. Same-Ref contention remains
   a real product risk, not solved by the packing change.
4. Reuse 58 completed clips when bindings/representation permit it; otherwise
   report the explicit migration/republication cost. Do not count test copies
   or abandoned Refs as corpus progress. Pin final package/build before launch.
5. Minimal acceptance: exact unique source/anchor accounting, committed media
   and vector counts, complete failure ledger, deterministic resume without
   duplicate logical items, and bounded real search→media playback samples.
   No all-video S3 reread, full-field compaction or new validation framework.

## Status / cleanup

No Slurm ingest job, S3 mutation or new scale-up spend was initiated this turn.
Existing pilot/packing evidence retained. The 9.7 MiB source inventory remains
because it is the proposed full-run input; unfinished ingest/bench worktrees
remain with local commits. No task build directories or media scratch created.
Await stage-1 approval and optionally the cluster tariff; the full-corpus goal
does not imply all later-stage budgets have already been approved.
