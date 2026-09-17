# Raw-page reuse at the public SDK boundary

Issue #16, 2026-09-16. Slurm 147492 (capture/probe, 33 s) and 147493
(training comparison), bos14-node-085, both COMPLETED exit 0. Same runtime as
ONDEMAND-RESULTS.md: released DreamDB 0.0.13, Python 3.12.3, Torch 2.9.1,
mjlab 1.6.0, MuJoCo 3.11.0, NumPy 2.5.3, Pillow 12.3.0. Requested one
RTX PRO 6000, 4 CPUs, 16 GiB. Capture snapshot (task data subsequently removed):
`d3hbzvdaxobehwyfcypjidtomlphdeeesnlqc52sxhaaxnlpit332`.

## Projection probe

Same eight contiguous ranges covering 256 records, alternating projection order.
No PNG decode in this probe. SDK timing includes native execution and conversion
to Python; collection timing is the application assembling returned Python rows.

| Projection | Returned bytes | SDK elapsed | Python collection |
|---|---:|---:|---:|
| image | 632,562 | 63.177 ms | .125 ms |
| sensor + action | 5,120 | 332.648 ms | .118 ms |
| all three | 637,682 | 386.129 ms | .186 ms |

The small arrays, not image byte volume or Python row collection, carry most of
this read cost. Source context at da55d61: iter_time_range invokes
fetch_array_field inside the anchor × array loop with serial await, and each
fetch does get_verified; blob reads have batched prefetch. Track reference maps
are assembled per query. These are possible contributors, not a sampled CPU/IO
profile or proof of installed-wheel revision. No core patch was made.

## Real training comparison

Same snapshot, request order, model, 156 windows, two epochs, 20 optimizer updates.
Both modes use the same bounded producer and a 1,048,576-byte cache budget. One
caches selected decoded records; the other caches raw projected pages (PNG stays
compressed), with decoded cache disabled. All four runs passed exact comparisons
of every delivered anchor/order, transformed image, sensor and target action.

| Execution order | Loop s | Input wait s | SDK calls | SDK s | PNG decodes |
|---|---:|---:|---:|---:|---:|
| decoded records | 5.007 | 4.747 | 145 | 4.580 | 696 |
| raw pages | .843 | .602 | 8 | .222 | 1,098 |
| raw pages | .861 | .620 | 8 | .244 | 1,098 |
| decoded records | 4.644 | 4.407 | 145 | 4.238 | 696 |

Paired elapsed speedups 5.94x / 5.39x. Page mode decodes *more* PNGs yet runs much
faster: avoiding repeated SDK reads dominates this fixture. Page hits/misses
148/8, evictions zero, retained payload peak 637,255 B. Decoded cache peak
1,046,180 B with 611 evictions. The same budget was used, not increased.

**The entire accessed compressed-page working set fits this cache.** This is not
a greater-than-cache benchmark or evidence of the same speedup at scale. The
probe ranges start at 1 while training pages align at multiples of 32, so probe
byte totals and retained training-page totals describe different ranges. Page
payload accounting also includes eight bytes per anchor, but excludes Python
container overhead and temporary copies. Budget is not a total-RSS guarantee.

Page mode first-batch elapsed .572 / .588 s (spawn, Reader setup, initial reads).
After the first batch, 19 queue waits total .0306 / .0338 s (~1.61 / 1.78 ms each).
These are host wait observations, not CUDA idle-time profiling. Total GPU compute
.194 / .194 s and completed transfer .0051 / .0051 s. Witness comparisons
.0286 / .0290 s are included in the loop and can overlap producer work too.
Loop excludes model/Torch setup and witness loading. No cold-cache reset.

Page-mode worker peak RSS 750,816 / 751,216 KiB, parent 1,440,160 / 1,439,892 KiB;
not additive unique physical memory. No prepared tensor files or persisted task
format. Window assembly, normalization and PNG decode remain task-time work.

## Meaning and next scope

The useful reuse boundary here is before repeated SDK reads, not after decoding
selected frames. Snapshot-local raw data reuse can serve different downstream
tensor transforms without freezing training semantics. This does not repair
first-pass array read performance. Before turning the prototype into guidance for
large datasets, measure a working set larger than cache and the native array read
path itself. Keep sampling semantics fixed; do not claim sequentially reordered
training is the same workload. No further cache sweep/core changes this round.

## Reproduce

In an isolated Slurm task directory, install private sdk/ as earlier examples,
copy this directory to source/, submit `source/pages.slurm probe`, then after
completion `source/pages.slurm train`. The second job reuses the first capture.
Parameters and paired order are in the script. Syntax and whitespace checks plus
the actual Slurm behavior were checked; no formal core testbox/CI verdict claimed.
Code and concise results are durable in the PR. Remove the isolated task data,
private SDK, logs and worktree after completion; shared runtime remains untouched.
