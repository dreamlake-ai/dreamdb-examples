# Application contract: snapshot episode-window reads

Status: first implementation target. This extends SPEC.md, not DreamDB's protocol.

## Identity and range

`EpisodeReader(backend, manifest, end_anchor, ...)` opens the exact Manifest,
never follows a moving Ref, and indexes the explicit prefix `[0, end_anchor)`.
Accept only `mjlab-reference-v1` with `logical-record-ordinal-v1` anchors. The
caller gets `end_anchor` from its capture receipt; absence of rows is not EOF.
No automatic traversal of unknown history or whole-timeline materialization.

An episode is `(env_id, episode_id)` within this reader's run/snapshot. Every
indexed episode starts with one reset, followed by uniquely ordered, contiguous
zero-based transitions. No transition follows a terminal/truncated transition.
An episode is complete only if its last transition has either terminal flag.
Clean `run_end` alone does not complete all episodes. Index prefixes may end in
incomplete episodes; reads reject them unless `allow_incomplete=True` is explicit.

Requests are ordered and may overlap or repeat:

- `StepWindow(env_id, episode_id, start, stop)`: transition steps `[start, stop)`;
  nonempty range, every requested step must exist. Reject missing steps, do not
  clip, pad or continue into the next episode.
- `TimeWindow(env_id, episode_id, start, stop)`: recorded `sim_time` in the
  finite interval `[start, stop)` inside that episode. This is post-action
  simulation time, **not** DreamDB `_anchor`/nanoseconds or wall time. It filters
  available transitions and can return zero rows. It does not assert that the
  entire interval was observed; incomplete-prefix use still requires opt-in.
  Bounds compare the stored floating-point timestamps exactly; no hidden epsilon
  or interpolation. Use step windows when integer transition boundaries are needed.

Reset rows are used for identity/completion, not returned as transitions.
Output preserves request order, then step order within each request. Repeated
requests deliberately produce repeated output. Each result carries its request,
snapshot Manifest, anchors and projected rows. `obs_after` remains `None` when
not recorded; `next_observation_valid`/terminated/truncated are never rewritten.
Callers must request the flags they need. No Torch tensor collation or implicit
zero padding. Returned arrays are copied per result so overlapping requests
cannot mutate each other's contents or cached reader state.

## Projection, limits and failure

Fields are a nonempty explicit subset of the recorded event fields. Never
default to the whole Schema; model bytes and run metadata are not payload fields.
Payload reads also project `kind` internally as an anchor carrier, so selecting
only an optional field does not erase transitions whose value is absent.
An initial metadata-only read identifies the format/dimensions, not the model.

Finite positive budgets: `max_scan_rows`, `max_requests`, `max_output_rows`,
`page_rows`. Validate requested scan width before I/O. Catalogue metadata grows
with transitions in the chosen prefix; it is not O(one training batch). The
unique integer ordinal format bounds returned rows per page by page width, but
this does **not** bound SDK Track/index metadata, connector caches or total RSS.
Array dimensions and caller-retained outputs also affect memory. No general
untrusted-input memory-safety claim.

Index identity reads are projected and page-bounded. Payload pages are fixed
ordinal pages clipped to the indexed prefix; each touched page is read once per
batch call even across duplicate/overlapping requests. No cross-call payload
cache: memory and freshness do not depend on eviction policy. Missing requested
anchors, malformed episode identity or SDK failures fail the whole call before
returning a partial result. An explicitly empty request list returns a batch with
no windows and no payload reads.

## Acceptance / excluded claims

Primary claim: real stored transitions can be selected into ordered episode/time
windows without crossing resets or changing values, and batched overlaps avoid
repeated payload page reads. A real public SDK round-trip and exact comparison
against known input is the sufficient evidence layer. Count actual public API
calls in that check to disambiguate batching; no synthetic private storage seam.
Check the same pinned reader after a later Ref append. Cover complete and explicit
incomplete episodes, optional next observations, repeated/overlapping requests,
and missing-step refusal in the same direct scenario.

Report index construction separately, then identical repeated batch requests
versus existing `read_episode`, with fields and ordering equal. Timings are local
observations; calls/rows are SDK boundary counts, not network GETs or object bytes.
No claim of random/global sampling quality, distributed loaders, persistent
catalogues, cross-run indexes, live-tail training, S3 scale or policy convergence.
