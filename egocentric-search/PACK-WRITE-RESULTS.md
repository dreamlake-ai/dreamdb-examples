# Opt-in video fragment packing — 2026-09-18

Primary claim: fewer media payload objects without changing fragment boundaries,
codec bytes or selective playback. Minimum evidence: the real public publisher
and reader, byte/frame comparison, plus observed payload GET ranges. The first
S3 comparison demonstrated a reachable full-read regression; fixing that reader
path, not expanding evidence machinery, was required.

## Implementation

Core branch `perf/video-item-leaf-writes`, base 0df51db, includes bounded
eight-way leaf writes (bc77082), opt-in packing (4335971), Python signature
snapshot correction (45a85fb), and selected-range coalescing (f01fc64).
Rust adds `publish_prepared_video_item_with_pack_target`; Python adds optional
`fragment_pack_bytes=0`. Zero preserves the existing standalone representation.
Positive targets concatenate adjacent fragments within one VideoItem using the
existing FragmentPack offsets. Singletons and oversized fragments remain
standalone; no transcoding, split, cross-video packing or new persistent format.
Packing copies payload bytes and the target is not a total-memory bound.

The reader combines only selected, physically contiguous ranges from the same
pack, verifies the combined range, then slices it back into the original
fragments. Unselected gaps are not bridged. Existing range-proof alignment is
unchanged. Dependency flush, parent publication and Ref CAS ordering remain.

## Checks

- Local testbox Linux image preflight, not a bound formal Evidence verdict:
  28 VideoItem tests pass (2 ignored); 17 writer-inventory tests pass.
- Direct product-boundary test: five fragments become three payload objects;
  narrow read remains exactly the selected range; full read uses three payload
  GETs and returns all original bytes. Existing failure/concurrency checks remain.
- Scoped Clippy succeeds with warnings (including a new clone-on-Copy warning);
  fmt and whitespace checks pass. No full-workspace or CI claim.
- Installed private wheel: Slurm 148016, 390 Python tests pass, 1 skipped.
  Initial 148013 signature snapshot omitted default `"0"`; corrected that
  snapshot, not the API behavior. 148014 and 148016 pass.
- Ingest unit tests: 244 pass, 1 skipped, 8 deselected; shell syntax passes.

## Real comparison scope

Two retained real clips, 22 fragments and 5,393 decoded frames each; source
Manifest `dztstcp2xjy33x4jvclqsdd67oejdoa7rjm55cbjvzz3kxx64rrpe`.
No new HF data, GPU work or full 58-video ingest. Same wheel for both modes,
alternating unpacked-a / packed-a / unpacked-b / packed-b, separate processes
and fresh isolated Refs. Packing target 16 MiB. Original-only stream copy.

Payload counts are actual S3 prefix enumeration, excluding init, metadata and
proof objects; they are NOT total HTTP requests or retry counts. First-range
read precedes full read on a reopened Dataset; this is not a system-cold-cache
claim. All runs check init/fragment hashes, encoded-stream bytes, all decoded
frames and range decoding. Network equivalence is not asserted.

### Intermediate regression, retained

Job 148015, core 45a85fb; private wheel SHA256
`4d0c9caa646c37b8c06145ea8c98bf8d752382d70a7fdff34824b77c8d83345f`.
All correctness checks passed. Packing reduced media objects 44 to 2 with the
same 23,380,763 payload bytes, but full reads fetched/verified pack ranges
separately per fragment. This result is not overwritten by the subsequent fix.

| Run | Publish, clips 1/2 (s) | Full read, clips 1/2 (s) | First range, clips 1/2 (s) |
|---|---|---|---|
| unpacked-a | 1.293 / 1.011 | 1.093 / 1.032 | 0.196 / 0.209 |
| packed-a | 0.953 / 0.915 | 1.916 / 1.916 | 0.240 / 0.242 |
| unpacked-b | 1.213 / 0.977 | 1.048 / 0.989 | 0.203 / 0.203 |
| packed-b | 1.345 / 1.109 | 2.857 / 1.935 | 0.251 / 0.250 |

### Coalesced reader comparison

Core `f01fc64a708f8147303d6a511bd77981a4e82337`, ingest runner ae951e0.
Private 0.0.14-labelled wheel SHA256:
`3638e28f9da2930c849bfa252ffca897917ba31ecaea203cf1acb99556794d7a`.
This is not a released package. Slurm comparison 148017.

Job 148017 completed exit 0 in 1m03s on bos14-node-099; all eight clip
publications/readbacks passed, with original byte/frame/range checks unchanged.
Both unpacked runs stored 44 payload objects, both packed runs stored 2;
all four stored exactly 23,380,763 payload bytes.

| Run | Publish, clips 1/2 (s) | Full read, clips 1/2 (s) | First range, clips 1/2 (s) |
|---|---|---|---|
| unpacked-a | 1.282 / 1.047 | 1.000 / 0.990 | 0.191 / 0.206 |
| packed-a | 1.109 / 0.920 | 0.315 / 0.314 | 0.233 / 0.276 |
| unpacked-b | 1.158 / 1.059 | 0.999 / 1.212 | 0.202 / 0.233 |
| packed-b | 1.034 / 0.901 | 0.319 / 0.323 | 0.268 / 0.240 |

Four-clip means: publication **1.137 → 0.991 s** (12.8% less), full read
**1.050 → 0.318 s** (3.31x observed), first-range **0.208 → 0.254 s**
(22.2% more). Payload object count falls 95.5%; fragment/time boundaries do not
change. These are two-clip observations, not throughput at corpus scale or
proof of minimum HTTP requests. The local direct check establishes coalescing;
the remote timings alone do not isolate every source of latency.

Run Refs are `ego100k-original-smoke-148017-{unpacked-a,packed-a,unpacked-b,packed-b}`.
Concise JSON reports (including final Manifest IDs and full fragment hashes)
are retained under local `artifacts/ego100k-400/pack-<run>-148017.json` and
cluster `runs/148017/<run>/original-smoke.json`. The intermediate 148015 reports
remain too. Packing stays opt-in because the single-range tradeoff is real.

## Reproduction and limits

In `dreamlake-ingest` use `spaces/ego100k/build_patched.sbatch` at the exact
core SHA with `EGO100K_PYTHON_VIDEO_TESTS=1`; verify the installed wheel and pin
its actual hash in `pack-compare.sbatch`. Submit through
`submit_pilot.py --task pack-compare`; credentials stay in process environments.
Reports include full Ref/Manifest IDs and fragment hashes. Rebuilding a wheel
can change its archive hash; do not blindly substitute it for the tested wheel.

No default ingest policy change, public release, push/merge or CI this round.
Multi-item metadata batching, total HTTP accounting and sustained same-Ref
write contention remain open. #397 remains deferred. No S3 deletion or GC.

## Cleanup / retained work

After jobs ended, task Docker target volume `ddb-video-pack-target` was removed;
shared Cargo/sccache and unrelated services were left alone. Slurm cleanup
148018 targets exactly the two comparison scratch directories, failed 4335971
build tree, intermediate/final target and build environments, final pytest
scratch, and transport archive. Exact successful private wheels and source SHAs
remain under cluster `core-45a85fb...` / `core-f01fc64...` for reproduction.
The local transport archive and redundant preflight logs are disposable after
this summary. Core `/Users/locatino/fortyfive/ddb-video-leaf`, ingest and bench
worktrees remain because their commits are unpublished and #400 is unfinished.
No credentials are archived; process exit does not revoke the three-hour STS
sessions. No S3 objects or test Refs were deleted.
