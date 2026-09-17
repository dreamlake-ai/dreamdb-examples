# Images and sensors from DreamDB into training

An external application reference: actual Cartpole state → PNG images,
sensor/action records → a pinned DreamDB snapshot → four-frame samples → a
small image/sensor regression model. It demonstrates storage-to-training data
delivery, not policy quality or a universal training framework.

**Status:** bounded CPU checks and real Linux/GPU capture/read/train experiments
validated. The current application dependency file pins `dreamdb==0.0.13`.
The later combined-core benchmark used private wheels; installing that package
version alone does not promise the same performance.

## Start with the application

Read [SPEC.md](SPEC.md) for record/sample meanings and [PLAN.md](PLAN.md) for
the original bounded implementation. The components are deliberately small:

| File | Application responsibility |
|---|---|
| `data.py` | Write records, pin a snapshot, select windows and decode selected PNGs/arrays |
| `run.py` | Generate the small real capture and run the baseline training/check workflow |
| `network.py` | The demonstration model, independent of DreamDB |
| `ondemand.py` | Optional bounded producer queue and explicit read/cache policies |

DreamDB supplies ordinary image/array/scalar storage and projected snapshot
reads. The application owns episode identity, ordinal anchors, train split,
window selection, normalization, tensor layout and model. The reader imports
DreamDB, NumPy and Pillow; simulation and Torch are needed only for their stages.

## Smallest run: CPU storage/reader check

From a checkout, with Python 3.12 and `uv` available:

```sh
cd multimodal-training
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -B run.py preflight
```

This uses generated tiny images and actual public SDK storage. It is not real
simulation or GPU-training evidence. The check cleans its generated temporary
data; the `.venv` remains for you to reuse or remove.

## Real capture and training

Use a compatible Linux/CUDA/EGL environment: the measured runs used mjlab 1.6.0,
MuJoCo 3.11.0, Torch 2.9.1+cu128, NumPy 2.5.3 and Pillow 12.3.0 with Python 3.12.
Install this application's SDK privately if reusing a shared runtime.

Inside a GPU allocation, from this directory:

```sh
python -B -u run.py all
```

This captures 8 worlds × 2 episodes × 16 steps, checks actual training inputs
against independent capture witnesses, runs the model and removes generated
data. It does not establish convergence or a useful learned controller.
For Slurm, `run.slurm` accepts `PROTOTYPE_PYTHON` and `PROTOTYPE_DIR`; set your
partition, GPU request and output path for your cluster. Do not train on a
scheduler controller.

To retain a capture for inspection, use a **new** task directory:

```sh
mkdir /absolute/new/task-directory
python -B -u run.py capture /absolute/new/task-directory
python -B -u ondemand.py exact /absolute/new/task-directory
```

`exact` selects only consecutive requested anchors; it preserves sample order
and uses a two-batch producer queue. It is opt-in: the default Reader retains
fixed-page selection. These individual commands retain the task's backend,
receipt and witnesses; remove that exact task directory when finished.

## Choose an alternative only when needed

[EXPERIMENTS.md](EXPERIMENTS.md) maps measured alternatives and their costs:
prefetch, decoded/raw-page caches, exact selection, core read optimization,
and optional prepared tensors/frame banks. Start there for performance work;
do not assume a ready format is necessary at ingestion.

Historical run commands and detailed prepared-format instructions remain in
[HISTORICAL-GUIDE.md](HISTORICAL-GUIDE.md). Most experiment Slurm scripts encode
the measurement cluster's runtime paths and must be adapted before use.

## Boundaries

The identity catalog is capped at 4,096 records and each request at 16 windows.
The reference is not a generic lazy multimodal stream, an arbitrary-scale
DataLoader, a download benchmark or a process-RSS guarantee. Results distinguish
SDK-returned payload from physical I/O and never use witness data as optimizer
input. Snapshot and input consistency matter independently of speed.

See [the repository contribution guide](../CONTRIBUTING.md) to adapt this pattern
to another application instead of growing this reference into a shared trainer.
