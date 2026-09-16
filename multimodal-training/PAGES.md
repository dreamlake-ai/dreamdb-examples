# Public read boundary and page reuse (issue #16)

Claim: repeated projected reads, rather than task tensor conversion, dominate the
current real training fixture. Determine which projection carries the cost before
choosing a reuse optimization. Observable evidence is wall time at the public API
for the same ranges and exact delivered input equality in the existing training
boundary. Do not infer internal CPU/IO attribution from aggregate elapsed time.

Plan: time SDK call separately from Python row collection. Profile all eight full
32-ordinal payload ranges with image-only, sensor/action-only and combined fields;
alternate projection order by page. This is a public boundary diagnostic, not a
new framework. Then choose one minimal read/reuse change, preserve task sampling,
and compare real optimizer loops with the existing producer and byte-bound policy.
No synthetic compute, no raw-format rewrite or prepared training artifact.

Source inspected at release preparation da55d61: Python iter_all_batches returns a
materialized PyList; Rust iter_time_range builds per-call lookups and assembles
selected fields, including per-anchor array reads. This is source context, not
proof of installed-wheel build provenance nor proof of which internal operation
dominates. Use the installed DreamDB 0.0.13 public API for the actual measurement.
