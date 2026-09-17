# Combined core read experiment (#22)

## Claim and contract

Measure whether the two native read changes improve the actual exact-range
training workload, not just their isolated regression fixtures. Public results
must remain identical for every training batch. The smallest sufficient check
is the existing independent anchor/pixel/sensor/action witness comparison
alongside loop, wait, SDK-time and returned-payload counters. No additional
validator or mutation framework; no claim about each patch's separate effect.

## Fixed inputs

- Baseline core: `c6b31ab307eaf4f2e8b56e0c71d8af9163142438`.
- Combined core: `aa4efd18c63e2e644d3bf81f7f5f119f850e956e`, a clean merge
  of PR #386 `263697a70796a26649b4601daa7df9c257770cf1` and PR #384
  `27b2709707d1975d4752e1492275d170e0e09b3e`. This is a benchmark branch,
  not main, a merge authorization, or a release.
- Application: exact-range mode from examples#21, no application caches;
  queue capacity two, 696 windows, two epochs, 88 updates per run.
- One real capture: 8 mjlab environments × 4 episodes × 32 steps.

## Plan

1. On a Slurm worker, build two private wheels with the same installed
   Rust 1.98.1 toolchain, maturin 1.9.6, Python 3.12 and unchanged release
   profile (opt-level 3, fat LTO, one codegen unit, overflow checks enabled).
   Record source and wheel hashes and build durations. A shared task-local
   target cache reduces build work; neither build duration is a benchmark.
2. Install each wheel to a separate task-private directory. No shared Python
   runtime changes, PyPI upload or production configuration changes.
3. In one GPU job, capture with baseline and execute exact mode in order
   baseline/combined/combined/baseline. Fix all other inputs. SDK version
   strings alone cannot identify these wheels; record native module paths.
4. Compare existing full input witnesses and report all four runs. Counters
   measure returned payload, not disk I/O. No OS-cache reset or cold-read claim.
5. Preserve conclusions and reproduction instructions, then delete task
   wheels/build directories, capture, raw logs and local temporary worktrees.
   Keep the exact source commits durably available for reconstruction.

The individual core PRs have passed testbox and CI. This run is the real
application integration measurement; it neither replaces those checks nor
starts another full CI run. No package version or core implementation changes.
