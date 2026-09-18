# Independent media leaf writes — 2026-09-18

Primary claim: independent Fragment publications can overlap without exposing
an incomplete VideoItem/Track/Manifest or advancing a Ref after failure. The
minimum evidence is a real publisher call with overlapping leaf PUTs and an
injected leaf failure, plus public readback. The concurrency ceiling is the
source-level `buffered(8)` invariant; no separate mutable seam or validator.

## Change and limits

Core candidate **bc770820191d3ca85eef9441572e0cd3fd04f90d**, directly based on
**0df51db7b2d2ae51ae219cb53a2936e91926e98e**. Fragment bodies changed from a
serial loop to bounded eight-way writes. All results are collected before an
error is propagated and failure flush runs. Pages and parents retain their
ordered publication, and the existing dependency flush and Ref CAS remain.
The input already owns all media bodies; eight is an operation-count bound,
not a total-byte or through-flush connector-memory guarantee.

This is **latency optimization, not request coalescing**: no leaf or publication
request was removed. Actual HTTP retries/counts were not measured. Multi-item
batch publication, request minimization and same-Ref fairness are still open.
No public API, persistent format, codec, GOP, retries or dataset scope changed.

## Local checks

Used local testbox image `ddb-testbox:1.97.0-7d7c440db3b8`, Rust 1.97.0,
isolated task target volume, existing shared Cargo/sccache caches. This is
ordinary Linux preflight, **not** a bound formal testbox Evidence verdict.

- `cargo test --locked -p dreamdb-dataset --lib video_item`: 27 pass, 2 ignored.
- `cargo test --locked -p dreamdb-protocol --test writer_inventory`: 17 pass.
- The new public-boundary check requires both Fragment PUTs to rendezvous,
  then verifies success readback or failure with unchanged handle/Ref and no item.
  Its connector refuses a flush while either fragment PUT remains unfinished.
- `cargo clippy --locked -p dreamdb-dataset --lib`: pass with existing warnings.
  An initial invocation wrongly added `-D warnings` (not the repository gate)
  and stopped on six existing connector warnings. Corrected the command, not
  project code or lint policy. No full-workspace or formal CI claim.
- `cargo fmt --all`, diff whitespace check; ingest unit suite 244 pass,
  1 skipped, 8 deselected. Shell scripts passed `bash -n`.

## Paired real S3 observation

Private wheel build Slurm **148010**, 1m02s, exit 0. Comparison **148011**,
1m17s, exit 0, bos14-node-099; eight CPUs / 16 GiB requested, no GPU.
Runner ingest **3f58235**. Both builds are private 0.0.14-labelled wheels, not
package releases:

- Baseline SHA256: `8618af52b1682e1a2babe695adbb38da39fc5f716ea19f774a55980b61b54d6e`.
- Candidate SHA256: `b4147916e795b0e48d2a311f02949167b961846036d534b5e3a09b69ea5271ca`.

Order: baseline-a, candidate-a, baseline-b, candidate-b; separate processes and
fresh Refs. Same two real clips from the pinned baseline, not extra corpus or
generated replacements. Each clip has 22 fragments and 5,393 decoded frames.
Timings cover `publish_prepared_video_item`, excluding source read/remux and
readback. No competing ingest ran. Network/cache equivalence is not asserted.

| Run | Clip 1 publication (s) | Clip 2 publication (s) | Result |
|---|---:|---:|---|
| baseline-a | 4.273 | 4.720 | PASS |
| candidate-a | 1.169 | 1.056 | PASS |
| baseline-b | 4.277 | 4.128 | PASS |
| candidate-b | 1.117 | 1.179 | PASS |

Four-publication mean: **4.349 s → 1.130 s**, observed **3.85x** (about 74%
less time). Not an end-to-end ingest or sustained-throughput multiplier.
Every run reopens and checks all init/fragment bytes, encoded-stream SHA256,
all decoded frame hashes/order, and a decodable interior range. Stored payload
is identical in size (11,990,185 / 11,392,434 B); source MP4 container-byte
identity is not claimed. No preview, lexical index or production write.

Refs are `ego100k-original-smoke-148011-<run>`. Final manifests:

| Run | Manifest |
|---|---|
| baseline-a | d2w6upaqx6mlvfxdz3p7nxu4jo67tdum2rlicz3yjfoseh75ppgg4 |
| candidate-a | d25huuztalikaoryujpdqc5ivoqw7bwh7u5r7xdfjofo56fzytsx2 |
| baseline-b | dzyf6ggfwiavgwmzclw63zntxo5scy4iozjloeowgr5ikhe3gg2ns |
| candidate-b | dzxycra46l4el6kpqpp23fkgp7va6jxvbzdbcoe2azqw3nvlhw5li |

## Reproduction and retained work

Build the pinned candidate with `EGO100K_CORE_SHA=bc770820191d3ca85eef9441572e0cd3fd04f90d`
and ingest `build_patched.sbatch`, then `submit_pilot.py --task leaf-compare`.
The latter pins actual wheel hashes: a rebuilt wheel with different bytes needs
an explicit updated pin, not a silently accepted replacement.

Small reports are in `/home/tom/ddb-ego100k-400/runs/148011/<run>/original-smoke.json`
and local `artifacts/ego100k-400/leaf-<run>-148011.json`.
Private wheels and source commits are retained. Task Docker target and source
transport archives are removed; Slurm 148012 confirmed removal of 265 MiB media
scratch, 1.9 GiB build target and 87 MiB build environment. No jobs remain.
Shared caches and all S3 objects/Refs are untouched. Redundant local preflight
logs were removed after retaining the commands and outcomes above.

Core worktree `/Users/locatino/fortyfive/ddb-video-leaf` remains on
`perf/video-item-leaf-writes`: local committed implementation, not pushed,
merged or released. Ingest and examples task worktrees remain for #400.
