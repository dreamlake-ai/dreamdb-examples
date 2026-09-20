# Original-only media and patched CAS rerun — 2026-09-17

Bounded continuation of core #400, not full-corpus ingest or closure.
Core: `0df51db7b2d2ae51ae219cb53a2936e91926e98e` (includes #401/#399/#396).
Private wheel, not PyPI: `dreamdb-0.0.14-cp38-abi3-manylinux_2_34_x86_64.whl`,
SHA256 `8618af52b1682e1a2babe695adbb38da39fc5f716ea19f774a55980b61b54d6e`.
Do not identify this run only by its unchanged package version.
Ingest source `c6d20a7`; examples workload `cb75fcf`.
Later ingest `394eaf6` only tidies imports/module re-exports; it was not the
deployed source of the reported cloud run.

## Setup and local boundary

Slurm build 147966 stopped before compilation: node Python lacked venv/ensurepip.
Official standalone uv 0.12.6 checksum verified; build 147981 completed (exit 0,
1m33s). No system packages or shared Python environment changed.
Local ingest unit tests: 244 passed / 1 existing skip. Initially omitting the
SDK caused an import failure in an existing test; supplying released 0.0.14
fixed that environment, not the test. New file-backed ingest-run test on the
private wheel: 1 passed in 1.21s, different HEVC init per item, reopened fragment
hashes, decoded-frame equality and an independently decodable interior window.
No new verification framework or formal CI run.

Cloud job 147987 ran sequentially on bos14-node-099, requested 8 CPUs/16 GiB,
no GPU. Slurm actually allocated 32 CPUs by its node allocation policy;
requested resources are not a measured CPU/RSS ceiling. Runtime 2m04s, exit 1
because the four-writer workload deliberately stopped (see below).

## Two real original clips

Sources are two distinct retained clips from pinned baseline
`dztstcp2xjy33x4jvclqsdd67oejdoa7rjm55cbjvzz3kxx64rrpe`, selected at positions
0 and 29 in the 58-clip metadata scan, with original MP4 SHA256 checked.
No HF download, preview, re-encoding or synthetic replacement.

New Ref `ego100k-original-smoke-147987`, final Manifest
`d2n4objajl7auhhuahqeyc7qru7xx774wl2sgukp7wiy4ktgb5abe`.
Each item has its own decoder init. All original encoded-stream SHA256 values
equal the reassembled stored streams; all 5,393 decoded frames per clip agree
in content/order. Full fragment/init byte checks pass after S3 reopen. Each
interior range also decodes using only its returned init/fragments.

| Observation | Clip 1 | Clip 2 |
|---|---:|---:|
| Source MP4 bytes | 11,986,318 | 11,388,563 |
| Stored init + fragments bytes | 11,990,185 | 11,392,434 |
| Fragment count | 22 | 22 |
| Stream-copy seconds | 0.038 | 0.041 |
| SDK publication seconds | 3.298 | 3.189 |
| Interior range bytes, including init | 561,141 | 516,633 |
| Interior range read seconds | 0.154 | 0.268 |

The 2-second fragment setting does not invent keyframes: maximum actual fragment
duration is 8.333333 seconds. Preserving the source codec/GOP implies this seek
granularity. Remuxing changes container bytes, so source-file byte equality is
not claimed. Stored bytes exclude protocol/index overhead and historical writes.
Range timings follow full readback on the reopened handle, not cold-cache or
browser-startup measurements. No browser compatibility claim.

## Same-Ref writes, same fixed 512 actual vectors

Batch 32, at most five attempts per batch, original seconds-scale randomized
backoff; fresh isolated Ref per level. Exact-reader CLI built at the same core
SHA, not the previous release tag. Every acknowledged anchor, identity digest
and exact f32 vector was reconciled by reopening. No lexical index.

| Writers | Outcome | Acknowledged | Explicit conflicts | Seconds including startup |
|---|---|---:|---:|---:|
| 1 | PASS | 512 | 0 | 26.684 |
| 2 | PASS | 512 | 4 | 32.497 |
| 4 | STOP | 384 | 11 | 34.788 |

At four writers, one worker acknowledged zero and exhausted five explicit CAS
conflicts; the other three acknowledged 128 each. Readback issues are empty at
every level, including the stopped case. There were no unclassified errors.
The 8/16 levels were not run. Do not relabel a partially completed workload as
PASS, increase retries post hoc, or claim the fairness problem is solved.

The earlier generic S3 409 error did not recur. HTTP response codes are not
counted by this workload, so this does not prove a 409 was exercised this time;
the mapping's direct HTTP-boundary test remains its status-specific evidence.
Two writers are slower than one on this fixed workload. No S3 throughput gain,
saturation, request minimum, or controlled old/new timing comparison is claimed.

## Remaining work and reproduction

- The original-only adapter path is implemented; the full bounded GPU ingest
  with source-derived embeddings has not run. Historical preview-derived vectors
  are not an equivalence baseline for the new source-frame spec.
- Same-Ref small-batch contention remains unsuitable as a scaling strategy under
  this retry budget. Batching and parallel preparation/independent branches are
  distinct choices, not an implicit retry-policy change.
- Actual HTTP request accounting, sustained larger workloads and cloud branch
  consolidation remain unverified. No automatic million-vector run.

Use `spaces/ego100k/build_patched.sbatch`, then
`submit_pilot.py --task patched-check --after-job <build>` in the ingest repo.
The smoke script reuses two source clips; the write workload reuses
`runs/147824/vecs/0000/0.npz` and its calibration. The task-specific endpoint
guard remains. New run IDs create fresh Refs; do not reuse these measured tips.
Concise outputs: `artifacts/ego100k-400/original-smoke-147987.json`,
`patched-jitter-{1,2,4}-147987.json` and `wheel-147987.sha256` on the local host.
No private video or credentials are checked into Git.

Old Refs/objects are unchanged; newly written test Refs/objects remain for
reproduction. No deletion, GC, business switch or package publication.
STS session expiry is 2026-09-17 17:23:54 UTC; process exit is not revocation.

## Cleanup / retained resumable state

Slurm cleanup 147998 completed on node-099, exit 0: removed the explicitly
recorded 46 MiB media scratch, 1.9 GiB task target tree and 132 MiB build venv,
plus source/tool transfer archives. Local partial uv download and transfer
archives were also removed. Shared caches and other jobs were not cleaned.
These disposable files are reconstructible; retained S3 sources were not deleted.

Keep for the unfinished original-frame pilot:

- `/home/tom/ddb-ego100k-400/core-0df51db7b2d2ae51ae219cb53a2936e91926e98e/wheels/`:
  exact private wheel (12 MiB), plus pinned source in its parent directory.
- `/home/tom/ddb-ego100k-400/bin/dump_exact_subset-0df51db`: copied and compared
  before removing target; 22 MiB exact-reader binary. The old target path is now
  absent, so use this retained path or rebuild before a new workload.
- `/home/tom/ddb-ego100k-400/runs/147824` and `runs/147987`: original real-vector
  input/calibration and compact rerun reports, respectively.
- `/Users/locatino/fortyfive/ddb-ego100k-ingest` and
  `/Users/locatino/fortyfive/ddb-ego100k-bench`: committed but unpublished adapter,
  workload and reports. Preserve until that application work is finished.
