# Selectivity and working-set boundary

Issue #18. Slurm 147494 (4m31s) and dependent 147495 (1s), bos14-node-085,
2026-09-16, COMPLETED exit 0. Real capture: 8 worlds, four 32-step episodes,
1,024 records; capture 20.05 s. Same runtime as PAGES-RESULTS.md, **released
DreamDB 0.0.13**, not core PR #384. Snapshot:
`d36rs7ipxnvf3ai5htclsmxt2dbxjoeg7shfq2y2iq353mwxi2dei` (task data removed).

Training env IDs 0–5, four-frame windows, 696 training windows, two epochs,
88 optimizer updates. Every run compared every delivered anchor/order, transformed
image, sensor and action with capture witnesses; all passed. Neither sample order
nor training semantics changed between modes. No prepared tensors or raw-format
conversion. This is larger than cache, not larger than machine RAM.

## Cache does not generalize from the tiny fixture

| Execution order | Loop s | Input wait s | SDK calls | SDK elapsed s |
|---|---:|---:|---:|---:|
| prefetch, no cache | 54.072 | 53.578 | 1,614 | 52.393 |
| prefetch, 1 MiB pages | 54.140 | 53.681 | 1,605 | 52.402 |
| prefetch, 1 MiB pages | 53.261 | 52.805 | 1,605 | 51.533 |
| prefetch, no cache | 52.404 | 51.887 | 1,614 | 50.783 |

No observed speedup: cached loops slightly slower in both pairs; no significance
claim from two pairs. Each cached run: 9 hits / 1,605 misses (0.56% hit rate),
1,593 evictions, peak retained payload 1,048,575 B within 1,048,576 B budget.
No decoded-record cache. Each run decodes 5,392 selected records; GPU compute
.294–.300 s, completed transfer .029–.030 s; >99% of loop waits for inputs.
Witness checking .112–.160 s is included and can overlap producer work.

First batch 2.488 / 1.868 / 1.795 / 1.785 s in execution order; initialization
and ordinary OS-cache effects are not isolated. Worker RSS 759,564–760,780 KiB,
parent 1,444,744–1,471,904 KiB (not summed unique RAM). A bounded array-payload
cache is not a total-RSS bound.

## Application page selection amplifies returned data

Counters cover training payload reads, excluding Reader's identity scan. Selected
records are unique within each batch, counted again across batches/epochs. Useful
encoded bytes count those records' PNG + sensor + action before tensor conversion,
not float tensors and not unique bytes over the entire run.

| Per run | No cache | Page cache |
|---|---:|---:|
| Selected record occurrences | 5,392 | 5,392 |
| Selected encoded bytes | 13,585,025 | 13,585,025 |
| SDK returned rows | 51,609 | 51,321 |
| SDK returned payload B | 129,675,661 | 128,949,547 |
| Returned / selected rows | 9.57x | 9.52x |
| Returned / selected payload bytes | 9.55x | 9.49x |

This is the application's 32-ordinal page plan followed by selecting scattered
windows. The SDK returns the ranges it was asked for; this is **not** evidence
that it ignores time filters. For the cached mode the ratio includes SDK misses
only over all useful deliveries; it is not a per-miss selection ratio. The same
sample order can be retained while a future read plan changes, but changing the
training shuffle itself would be a different comparison.

## File-read observations at the public boundary

Separate probes on the same capture, not timed as performance runs. `strace -f`
observed openat/read/pread64 with resolved descriptors; markers exclude Python
startup and snapshot open. Successful read byte returns include OS-cache-served
bytes, **not disk-device IO or network transfer**. EOF reads contribute zero;
file metadata syscalls are not measured. No raw traces are archived.

| Query | Returned rows / bytes | Array payload file B | Image payload file B | Track file B |
|---|---:|---:|---:|---:|
| sensor/action [97,129) | 32 / 640 | 640 | 0 | 79,700 |
| image/sensor/action [97,129) | 32 / 80,372 | 640 | 79,732 | 125,320 |
| image/sensor/action [97,101) | 4 / 10,118 | 80 | 10,038 | 125,320 |
| same four-row query again, same handle | 4 / 10,118 | 80 | 10,038 | 45,620 |

First array probe: 64 Item paths + two Track paths. Combined 32-row probe:
64 array + 32 image + three Track paths. Four-row probe: eight array + four image
+ three Track paths. Repeated probe: eight array + four image + **one image
Track**. Direct trace paths establish the latter's `image.png/track/` identity.

Projection therefore avoids unselected image payload in the tested case; narrower
ranges fetch only the corresponding payload Items. The first four-row query has
135,438 total file bytes / 10,118 returned bytes (~13.39x), while repeating on the
same handle removes the two array Track reads but still reads 55,738 bytes
(~5.51x). Do not report first-open Track reads as an all-query persistent cost.
Conversely, the image Track reread is directly observed, not inferred from timing.
This checks these Image + dense-array fields, not every modality or storage form.

## Next work

Two distinct opportunities, not a larger-cache prescription:

1. Reduce application overfetch through a bounded batch-selection read plan that
   preserves requested anchors/order; first assess existing APIs before adding one.
2. Investigate repeated fragment Track work in core, reusing immutable decoded
   metadata only with its current Manifest validation intact.

Generic streaming/backpressure is still unverified. Tests here use an explicitly
bounded catalogue and batches; increasing to 1,024 rows does not prove unbounded
scan memory safety. No extra capacity sweep or further optimization in this slice.

## Reproduce and cleanup

See AMPLIFICATION.md and the two Slurm scripts. Submit amplification.slurm from
an isolated source/ + sdk/ task directory. After completion submit
amplification-repeat.slurm; run trace_reads.py with each trace and backend path.
The extra repeated probe disambiguates first-use metadata from repeat-query cost,
not a test of the tracing tool. Exact input checks use the existing training
boundary. Syntax/whitespace checks and these real runs passed; no core/testbox
verdict or formal CI run is claimed for this examples-only change.

Code and concise findings are preserved; task capture, private SDK, trace/log
files, caches and worktree are removed after durable push. Shared runtime and
unrelated tasks remain untouched.
