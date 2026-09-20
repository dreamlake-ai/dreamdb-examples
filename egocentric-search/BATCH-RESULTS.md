# Fixed-work batching — 2026-09-18

Slurm 148007, same private core `0df51db7b2d2ae51ae219cb53a2936e91926e98e`
wheel and exact-reader binary as the patched checks. Ingest runner commit
`9c898ec` (only documentation changed after submission). Eight CPUs / 16 GiB
requested, no GPU; scheduler allocation is not a measured CPU/RSS ceiling.

Primary claim: larger application batches can reduce fixed-work publication
time without losing acknowledged data. Minimum evidence is the actual S3 append
followed by reopened anchor/digest and exact-f32 reconciliation. No new testing
framework, retry policy, or synthetic vectors.

All cases use the same first 512 real vectors from pilot 147824 and the same
calibration. Fresh isolated Ref per case; same-Ref mode, five attempts per batch,
seconds-scale jitter. Sequential runs, no concurrent ingest. Times include
worker startup, exclude dataset creation and verification; not HTTP counts.

| Writers | Batch | Wall seconds | Explicit conflicts | Acknowledged | Result |
|---|---:|---:|---:|---:|---|
| 1 | 32 | 26.767 | 0 | 512 | PASS |
| 1 | 128 | 9.892 | 0 | 512 | PASS |
| 1 | 512 | 5.729 | 0 | 512 | PASS |
| 4 | 128 | 27.310 | 6 | 512 | PASS |

Every case has zero readback issues, including exact vector bytes. Single-writer
batch 512 is 4.67x faster than batch 32 in this observed pair. Four writers
batch 128 do not beat one writer batch 128. This does not establish sustained
throughput, network saturation, minimum requests, or general fairness. The
earlier four-writer batch-32 STOP remains a failure under its own retry budget;
this is a separate batching strategy, not a continuation of that staircase.

Reproduce using `spaces/ego100k/submit_pilot.py --task batch` in the ingest
worktree after deploying that revision. Exact results live at
`/home/tom/ddb-ego100k-400/runs/148007/batch-*.json`, with a small local copy in
`/Users/locatino/fortyfive/artifacts/ego100k-400/`. Do not reuse measured Refs.
