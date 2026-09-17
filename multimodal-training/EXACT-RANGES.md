# Exact training ranges — reference experiment (#20)

## Contract

This application-level policy uses the existing projected TimeRange API. For
each batch, deduplicate the required anchors, subtract decoded-cache hits,
sort, and merge only consecutive missing anchors. Split any run at `page_rows`
to retain the existing per-call row bound. Read only image/sensor/action;
reconstruct samples in their original requested order, including repeated
anchors across overlapping windows. Never merge across a gap merely to save a
call. No dataset, training input, transform, SDK or wire-format changes.

The fixed-page policy stays the default and comparison baseline. The `exact`
training mode uses the same two-batch producer queue as `prefetch`, with both
application caches disabled. It is not a new DreamDB API or training product.

## Primary claim and minimum evidence

Exact ranges eliminate neighboring-row overfetch on this dense ordinal fixture.
The observable failures are incorrect/missing/reordered training values or
returned payload that still exceeds selected payload. Existing independent
per-batch witness checks cover anchors, transformed image pixels, sensor and
action values; existing counters cover rows, bytes and calls. No additional
validation framework, mutation layer or timing assertion is needed.

Fewer bytes does not imply faster execution: fragmented selection may require
more SDK calls, each with metadata and conversion costs. Measure the tradeoff.

## Implementation and run plan

1. Add a Reader range-selection option; keep identity scans and fixed-page
   default unchanged. Thread it through the existing producer as `exact` mode.
2. Use one real mjlab capture: 8 environments × 4 episodes × 32 steps, same
   format as examples#19. Keep DreamDB 0.0.13 and the existing shared runtime;
   no shared environment changes or unmerged core patches.
3. One isolated Slurm GPU job: capture, then prefetch/exact/exact/prefetch,
   two epochs and 88 updates per run. Existing witness checks on every batch.
4. Record loop/wait/SDK time, SDK calls, returned and selected rows/bytes,
   decode count, and observed RSS. Identity scan is outside payload counters
   but remains inside startup/first-batch timing. No disk/network throughput
   claims or cold-cache claims. Four runs establish a fixture result, not a
   distribution-wide performance guarantee.
5. Preserve concise conclusions and reproduction instructions in this repo;
   remove task capture, witnesses, private SDK, logs and worktree after push.
