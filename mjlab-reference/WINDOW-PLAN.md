# Episode-window design and implementation plan

Issue: dreamdb-examples#4. Parent: prototype PR #3, pinned `c28ba6d`.
Do not merge the parent or change its writer/playback implementation as part of
this work. No initial DreamDB core change or package release.

## Design

One small `windows.py` module:

1. Open by Manifest and read only metadata at ordinal zero; validate the existing
   application format. Scan identity/step/time/terminal columns in explicit
   finite ordinal pages, building a per-episode list of transition descriptors.
2. Resolve StepWindow/TimeWindow requests against those descriptors (step offsets
   and binary search of nondecreasing simulation time). Validate
   completion and output budgets before payload I/O. Record requested anchors.
3. Union touched payload pages; read each once with explicit projection through
   `iter_all_batches`. Retain only selected rows, not over-read neighbours.
4. Assemble independent per-request results in caller/step order. Copy array
   payloads at the result ownership boundary, retain absent values as None.

Separate `ReadStats` for index/payload windows and rows returned. These count the
calls the implementation actually makes; they are not connector instrumentation.
No asynchronous prefetch or worker pool before a measured need. The one-time
identity scan trades initialization work for avoiding per-request global scalar
anchor materialization; expose that tradeoff rather than hiding it.

## Implementation / validation sequence

- Contract first: WINDOW-SPEC.md defines clocks, prefix, completeness and limits.
- Implement the reader; no mutation of original data or private SDK calls.
- `check_windows.py`: bounded CPU-only fixture built using the existing writer
  and a real minimal MuJoCo model. Known interleaved episodes, complete and
  incomplete tails, exact typed arrays. Reopen pinned data, exercise requested
  windows and compare values/anchors; instrument the public window call only to
  establish overlap deduplication. No test of this instrumentation itself.
- Compare identical requested windows against existing `read_episode`; report
  one-time index cost, warm payload cost, actual SDK call/row counts and output
  volume. No benchmark pass/fail threshold from noisy elapsed time.
- Use the existing local storage environment; no GPU/Slurm job is required for
  this read-only application logic. If a generic core change becomes necessary,
  stop and state the newly reachable risk, then use core issue/spec/testbox flow.
- Update README/design/results, submit one formal PR (stacked until #3 merges),
  clean task data, environment, logs and worktree after durable preservation.

Stop after the direct claim passes. Do not add a benchmark service, query planner,
cache framework, validator controls or new mutation matrix for this prototype.
