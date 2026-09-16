# Bounded decoded-record reuse (issue #14)

Primary claim: a byte-limited, snapshot-local decoded-record cache can reduce
repeated raw reads/PNG decode while preserving on-demand training inputs. Failure
is different delivered inputs/order, cache payload exceeding its budget, or no
useful reduction in repeated work. Minimum evidence: the existing real training
boundary's exact witness comparisons plus direct timing/counters; no new harness.

First separate public range read, selected PNG decode/validation, assembly and
task float conversion time. Then compare no cache against a 1 MiB LRU of uint8 RGB,
sensor/action arrays keyed by anchor within a Reader pinned to one Manifest.
No task window tensors, normalized floats or random augmentation enter the cache.
The budget covers retained array payload only, not Python overhead, SDK buffers,
batch references, IPC, or total RSS. Oversized entries bypass it.

The 192 training records need more than 1 MiB; this deliberately cannot retain the
entire training set. Hits are resolved before reading missing anchors' pages;
selected misses alone are decoded and offered to the cache. Preserve sample
ordering and the existing maximum 16 requests / 32-row public range pages.

Implementation: optional Reader cache, zero-budget default preserving callers;
reuse the spawned producer and real optimizer workload. Run no-cache/cache/cache/
no-cache on one real capture via Slurm; no sweep or artificial compute. Report
stage times, hits/misses/evictions, peak retained bytes, input wait and loop time.
Warm small local results do not establish remote/large-dataset performance or a
general cache invalidation product. Document conclusions, open stacked PR, clean.
