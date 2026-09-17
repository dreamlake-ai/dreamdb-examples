# Egocentric-100K semantic-search and concurrent-write benchmark

**Experimental; bounded real pilot, concurrent-write measurements in progress.** Tracks
[core #400](https://github.com/dreamlake-ai/dreamdb-core/issues/400).

This application turns permitted real video into frame embeddings and previews,
then measures DreamDB reads and writes. It is not a new benchmark framework or
a production ingestion service. Domain sampling, frame timestamps, encoding and
queries belong to the application; object storage, snapshots, indexes and Ref
publication belong to DreamDB.

Read [SPEC.md](SPEC.md) and [PLAN.md](PLAN.md) before running anything.
Start with source metadata selection:

```sh
uv run --with huggingface_hub python egocentric-search/select_inputs.py \
  --output /path/to/task/pilot-inputs.json
```

Requires your own HF login with access to builddotai/Egocentric-100K. The command
pins the source revision, selects known-size shards across factories/workers,
and downloads **no video**. It refuses to overwrite an existing output. Keep
the output for the run; never put credentials in it. No GPU or DreamDB package
is needed for this metadata-only command. Runtime dependency versions are
recorded in its output; it does not establish SDK compatibility.

The GPU adapter/pipeline lives in `dreamlake-ai/dreamlake-ingest`,
`spaces/ego100k/` (task branch `feat/ego100k-pilot`, not yet merged). Do not copy
another dataset's legacy ingest commands. Tested SDK is released dreamdb 0.0.14;
model/tokenizer and runtime pins are in the adapter. This example owns the
workload, comparisons and results, not a second ingest engine.

See [PROGRESS.md](PROGRESS.md) for the current measured scope. The first real
run stores 58 clips and 10,440 vectors, not the full 100K-hour corpus. Its source
and preview bytes were read back and checked; semantic query probes pass.

`write_stress.py` runs one explicit concurrency level using actual precomputed
vectors. It needs Python 3.12, dreamdb 0.0.14, NumPy, S3 credentials scoped to an
isolated bucket, the pilot's vector shard/calibration file, and the existing
`dump_exact_subset` binary compiled from core `python-v0.0.14` for exact readback:

```sh
export DDB_EXACT_READER=/path/to/pinned/dump_exact_subset
python egocentric-search/write_stress.py \
  --vectors /path/to/pilot/vecs/0000/0.npz \
  --calibration /path/to/pilot/calibration.json \
  --backend "$BENCH_BACKEND" --mode independent --writers 1 \
  --rows 512 --batch 32 --out /path/to/results/independent-1.json
```

The script refuses other remote buckets than the task bucket in PLAN.md. To
adapt it, explicitly replace that isolation guard; do not point at production.
Success requires fresh-read anchor/digest agreement and exact vector bytes,
not just append return values. Ordinary Python scans of compressed fields
return lossy reconstructions, even when rerank is enabled; they are NOT an
exact-vector export interface. The script uses the existing exact-sidecar CLI,
not a hand-rolled protocol parser. No lexical index is involved.

`resolve_hit.py --queries <semantic-queries.json> --backend "$BENCH_BACKEND"
--out <new.json>` links a real frame hit to its clip using this application's
one-hour anchor stride. It verifies original and preview digests. This is an
explicit application mapping, not implicit temporal hydration by DreamDB.

`read_stress.py --pilot <pilot-run-directory> --out <new.json>` measures a
bounded 320-query retrieval-only staircase on four actual image embeddings;
the earlier text prompts remain the separate text-to-video functional check.
`media_stress.py` accepts the same arguments and writes the first 16 real clip
pairs to isolated independent Refs at each concurrency level. See SPEC.md for
fixed budgets, projections, content checks and exclusions. These scripts are
Slurm workloads, not controller/laptop stress commands.

Each case creates fresh Refs and retains them for diagnosis. Unknown publish
outcomes stop; only explicit conflicts have bounded reopen/retry. Request counts
are not measured yet; phase timings must not be relabelled as wire throughput.
Use Slurm for compute and the dedicated private S3 bucket recorded in PLAN.md.
S3 retains both original MP4 bytes and derivative previews, plus embeddings and
necessary metadata. Preserve original-video bytes and their source identity for
later experiments; do not mislabel a remux/transcode as the original. Source TAR
archives need not be uploaded. Clean temporary node copies only after durable
upload is confirmed; do not delete retained S3 originals as scratch cleanup.

Task-local outputs, environments and node scratch must be removed after needed
results are recorded. S3 cleanup is an explicit run-specific operation, never a
recursive deletion against another dataset or a production bucket. No automatic
expiration is configured; report retained data and costs rather than forgetting it.
