# Selectivity and a larger-than-cache working set (issue #18)

Primary questions: do requested fields/ranges avoid unrelated data, and does the
raw-page cache still help when the real task working set exceeds its budget?
Observable failures are unrequested values, changed training input/order, reads
of unprojected media, or cache thrashing/continued input wait. Direct evidence is
the existing public read/train boundary, its row/byte counters, plus bounded
strace of successful object-file reads. No new validation framework.

Plan:
1. Real mjlab capture: 8 worlds × 4 episodes × 32 steps = 1,024 records. Keep
   image size, fields, policy, four-frame windows and training env IDs 0–5.
2. Derive expected windows from capture identities, not fixed 256-row constants.
   Compare no-cache producer and 1 MiB raw-page producer in reversed pairs on
   the same data, with exact per-batch witness checks and real optimizer work.
3. Count unique selected records per batch, useful encoded source bytes, SDK
   returned rows/bytes, page hits/misses/evictions and cache peak payload. These
   counters do not by themselves measure object fetches or physical disk IO.
4. Separately trace public field/range probes using strace on the local backend.
   Read bytes from successful read/pread syscalls are filesystem bytes delivered
   to the process, not disk-device bytes; OS caching remains. Exclude startup and
   snapshot-open using explicit start/end markers; retain concise totals, not logs.

Use released Python 0.0.13 so comparisons share one reader. Do not attribute these
results to the unmerged core #384 optimization. Do not reorder training for IO or
increase cache to make the dataset fit. This is larger than a 1 MiB cache, not
larger than host RAM, and not a test of generic streaming/backpressure yet.
