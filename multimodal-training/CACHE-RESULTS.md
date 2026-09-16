# Bounded record-cache result

Issue #14; Slurm 147491 on bos14-node-085, 2026-09-16, COMPLETED exit 0,
60 s including capture and four independent training processes. Same runtime as
ONDEMAND-RESULTS.md (DreamDB 0.0.13). Requested 4 CPUs / 16 GiB / one RTX PRO 6000.
Ephemeral capture snapshot:
`d2bzs6snasd7zvzchhb3375darznwjggm2rutqvam2exa3frkufeg`.

One capture, same 156 training windows / two epochs / 20 updates, same shuffle.
All four runs compared every delivered anchor/order, transformed pixel, sensor
and action against independent capture witnesses; all passed. No ready artifact.

| Execution order | Loop s | Wait s | Public read s | Decode/validate s | Assemble s | Float/layout s |
|---|---:|---:|---:|---:|---:|---:|
| prefetch, no cache | 5.528 | 5.271 | 5.080 | .0944 | .00347 | .00757 |
| prefetch, 1 MiB cache | 4.671 | 4.419 | 4.254 | .0723 | .00392 | .00757 |
| prefetch, 1 MiB cache | 4.664 | 4.416 | 4.257 | .0685 | .00376 | .00847 |
| prefetch, no cache | 4.970 | 4.722 | 4.582 | .0913 | .00379 | .00747 |

Paired loop reductions: 15.5% / 6.2%, not a stable general speedup estimate.
Completed GPU compute .196–.207 s; transfer .0052–.0063 s; witness comparisons
.030–.034 s, included in loops (producer can overlap comparisons too).
First batch .923/.599/.606/.580 s in execution order, including worker/Reader
startup; no evidence that cache improves first-use latency.

| Counter per run | No cache | Cache |
|---|---:|---:|
| Projected SDK calls | 156 | 145 |
| Selected PNG decodes | 1,098 | 696 |
| Cached selected records hit | 0 | 402 |
| Cache evictions | 0 | 611 |
| Peak cache array payload B | 0 | 1,046,180 |

The peak fits 85 source records of 12,308 B each, less than 192 training records.
The budget is 1,048,576 B. A runtime assertion after admission enforces the payload
bound; observed evictions demonstrate this was not an all-data cache. Cache owns
copies so source array views cannot silently retain larger SDK allocation buffers.
Batch references, temporary copies and Python metadata are outside this retained
payload budget; there is no whole-process memory guarantee. Worker peak RSS was
750,436–751,100 KiB; parent 1,439,996–1,457,532 KiB, not summed as unique RAM.

## What this establishes

Public reading occupies ~98% of producer read/convert work in both modes. This
includes SDK execution, Python conversion and row collection; it does not isolate
storage IO, B-tree traversal, decoding inside the SDK, or binding overhead. PNG
decode outside the SDK is under 0.1 s. Optimizing float layout is not the next
useful target for this workload.

Caching cuts PNG decodes 36.6%, but calls only 7.1%. A batch's misses still touch
most 32-row pages, so selected-record reuse does not eliminate most page reads.
Despite improvement, ~95% of cached loop time still waits for input. No theoretical
limit, remote bandwidth, cold-cache, or large-dataset claim follows.

Next useful question is inside the public projected read boundary, or reuse at
its page/object granularity. Do not infer the storage engine itself is slow from
this aggregate. Keep requests/order fixed before comparing a different read plan;
avoid changing training sampling just to obtain a convenient IO pattern. Any page
cache must remain byte-limited and snapshot-specific. Not implemented this round.

## Reproduction and cleanup

Use cache.slurm with the same isolated source/ and private sdk/ setup described in
ONDEMAND-RESULTS.md. It captures once and runs prefetch/cached/cached/prefetch.
No core edits, manual CI run, or core testbox verdict. Code and concise results
are retained in the PR; task capture, private SDK, caches, raw logs and worktree
are removed after the completed job and durable push. Shared runtime is untouched.
