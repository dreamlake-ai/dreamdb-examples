# Egocentric-100K semantic-search and concurrent-write benchmark

**Experimental; no stress result yet.** Tracks
[core #400](https://github.com/dreamlake-ai/dreamdb-core/issues/400).

This application turns permitted real video into frame embeddings and previews,
then measures DreamDB reads and writes. It is not a new benchmark framework or
a production ingestion service. Domain sampling, frame timestamps, encoding and
queries belong to the application; object storage, snapshots, indexes and Ref
publication belong to DreamDB.

Read [SPEC.md](SPEC.md) and [PLAN.md](PLAN.md) before running anything.
Only source metadata selection is currently implemented:

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

The actual GPU pipeline and query/write runners are pending. Do not infer that
the commands from another dataset's example operate on this source correctly.
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
