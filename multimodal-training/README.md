# Images and sensors from DreamDB into training

Small external reference application for [issue #6](https://github.com/dreamlake-ai/dreamdb-examples/issues/6).
Read [SPEC.md](SPEC.md) and [PLAN.md](PLAN.md) first. This is not a training product
or a universal DreamDB streaming implementation.

Status: local public-SDK preflight and one real Slurm capture/read/train run passed.
See [FINDINGS.md](FINDINGS.md) for exact results and limitations.

Actual Cartpole state → RGB PNG + sensor + action records → pinned DreamDB
snapshot → four-frame windows → small image/sensor behavior-cloning regressor.
The applied demonstration controller is state feedback, not a trained expert;
successful data delivery and optimization do not imply a useful learned policy.

## Run

CPU preflight (tiny generated images, not real-scene acceptance):

```sh
cd multimodal-training
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -B run.py preflight
```

Real run requires Linux, CUDA/EGL and the existing compatible mjlab runtime:
Python 3.12, mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1+cu128, NumPy 2.5.3,
Pillow 12.3.0, and DreamDB 0.0.13. Install the SDK into a private import directory
if reusing a shared environment; do not modify it in place. No RSL-RL required.

```sh
export PROTOTYPE_PYTHON=/absolute/path/to/compatible/python
export PROTOTYPE_DIR=/absolute/path/to/multimodal-training
sbatch --partition=YOUR_PARTITION --gres=gpu:YOUR_GPU_TYPE:1 \
  --output=/task/scratch/run.log "$PROTOTYPE_DIR/run.slurm"
```

The coordinator invokes capture and train as separate processes with 240-second
phase limits. Eight worlds, two 16-step episodes per world, 64x64 images, two
training epochs. It removes the generated dataset, witness arrays and caches on
exit. Set TMPDIR to task-local scratch if appropriate. Individual `capture DIR`
and `train DIR` modes keep their data for diagnosis; users must clean that DIR.
The user-created `.venv` remains until explicitly removed.

`data.py` depends only on DreamDB, NumPy and Pillow. Image decoding, sample
definition, split and Torch tensors are application responsibilities. Images are
native Image fields, not embeddings or opaque text. It neither follows a moving
Ref nor accesses private storage objects. Every training batch is read through
public projected reads; witness arrays are only for acceptance, never optimizer
input. Images are normalized to [0,1], sensor values remain in recorded units.

## Performance boundaries

One small catalogue holds identities/flags, capped at 4096 records. Batch requests
are capped at 16 and share 32-row payload pages; selected PNGs are decoded once
per batch. Calls can return unselected neighboring rows: report this amplification,
not just useful bytes. There is no cross-batch payload cache, asynchronous prefetch,
DataLoader worker pool, persistent selection index or total-RSS guarantee.

Compare identical requests using one window per call and batched calls, alternating
order by group. Report actual SDK call count, returned payload bytes and decode
count. These are not object GETs or physical disk/network bytes. Timings include
ordinary OS caches, which are not reset. The later training run is consequently
not a cold-read benchmark. Catalogue, first batch, read/compare, and synchronous
loader+transfer versus GPU compute times are separate. No speed threshold or
production recommendation is inferred from this fixture.

This first slice composes existing materializing range calls into bounded pages.
Generic lazy multi-modality streaming remains a distinct core capability; neither
the page size nor this small success proves billion-row memory behavior.

## Training-ready inputs: two delivery stages

[STAGES.md](STAGES.md) defines the next slice ([issue #8](https://github.com/dreamlake-ai/dreamdb-examples/issues/8)).
It moves PNG decode, float conversion, normalization and NCHW window construction
into an explicit, reusable upstream materialization. No cost disappears: four-frame
float32 windows occupy substantially more bytes than the compressed source.
The first real two-stage run passed; see [STAGES-RESULTS.md](STAGES-RESULTS.md)
for the measured preparation cost, 47.8x artifact expansion and local input timing.

```sh
# CPU check of materialize → byte delivery → mmap:
.venv/bin/python -B pipeline.py preflight

# Inside the same bounded Slurm allocation as the real run:
python -B -u pipeline.py all
```

The coordinator runs capture, the original PNG-based read/train path, then:

```sh
python -B -u pipeline.py prepare /task/capture     # upstream build → ready/
python -B -u pipeline.py deliver /task/capture     # local byte-copy + digest → delivered/
python -B -u pipeline.py train-local /task/capture # only delivered/ is needed
```

`prepare` needs that directory's backend and receipt. Both output directories must
be new; there is no resume/overwrite or cache replacement policy in this reference.
`deliver` is a local transport baseline, not a MinIO/S3 downloader or a network
benchmark. The design makes those transports byte-only; remote speed is not this
slice's priority. The ready manifest is copied last after all tensor files verify.
This is application completion, not an fsync crash-durability guarantee.

`train-local` imports no DreamDB connector or image decoder and needs neither the
original database nor capture witnesses. It maps immutable float32 arrays, gathers
requested samples straight into a reusable pinned host batch and transfers them
to a reusable GPU batch. It synchronizes a CUDA completion event before declaring
inputs ready; no hidden normalize/transpose in the loop. Arbitrary sample shuffle
still needs gathering and host-to-device copies. No async prefetch/compute overlap
or GPU-direct storage is claimed.

The acceptance-only `verify-local` mode also checks all ready tensors against
capture witnesses, requires the original source path to be absent, and checks one
completed device copy exactly. `pipeline.py all` runs it after renaming its own
temporary source, then cleans the entire task directory. The witness check warms
file pages; these measurements are not cold-storage or theoretical memory limits.
Use plain `train-local` for independent local-only consumption without witnesses.
