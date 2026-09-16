# mjlab / DreamDB reference prototype

Status: **bounded capture, independent playback and real PPO integration validated**.
Recording overhead is measured and remains too high for a large-scale training
recommendation. This is a reference design, not a production-ready training recorder.
Tracked in [issue #2](https://github.com/dreamlake-ai/dreamdb-examples/issues/2).

This example has two purposes:

1. Show how an external application defines its own domain semantics on top of
   DreamDB, using parallel robot-simulation recording and state playback.
2. Act as a real DreamDB user: expose public-API, correctness, usability and
   performance problems, and drive appropriately scoped improvements.

It is not a new product, a supported RL integration framework, or a proposal to
put episodes, policies or MuJoCo into DreamDB core. The reusable output is the
design, its tradeoffs and a small runnable example, not a plugin architecture.

Read in order:

- [Application contract](SPEC.md): what records mean and what is guaranteed.
- [Design](DESIGN.md): how the prototype maps that contract onto public APIs.
- [Implementation plan](PLAN.md): bounded milestones and acceptance.
- [Findings](FINDINGS.md): source observations, measurements and product feedback.
- [Adapting the pattern](ADAPTING.md): what another application should reuse/change.

The first target is mjlab's built-in `Mjlab-Cartpole-Balance`, one GPU and a
small number of parallel worlds. Cartpole is a minimal integration workload,
not evidence of humanoid-training performance. Playback reads stored physical
state; it does not replay a policy or claim deterministic action resimulation.

## Boundaries

The application owns task configuration, episode identity, reset semantics,
state encoding and playback. DreamDB supplies ordinary fields, batched writes,
published snapshots and queries. Ordinary DreamDB users acquire no simulation
dependencies. This example's users install mjlab/MuJoCo/PyTorch because they run
this application.

## Run the storage slice

Requires Python 3.12 and `uv`. This runs on CPU; it does not require mjlab/Torch,
Slurm, a graphics context or a GPU. MuJoCo compiles and reloads a tiny synthetic
model as an asset-storage check; this is not the mjlab task or playback test.

```sh
cd mjlab-reference
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-storage.txt
.venv/bin/python -B check_storage.py
```

The coordinator starts a writer process, waits for its exit, then starts a reader.
It checks 11 exact event rows across two environments, three complete episodes,
two incomplete tails, projected state reads, a prior pinned snapshot and loading
the saved model. Arrays are compared by dtype, shape and bytes; floats by bits.
Generated datasets and model files are automatically removed, including on test
failure. The user-created `.venv` remains for subsequent work; remove it when done.

`store.py` is a synchronous local-filesystem primitive; `writer.py` owns it in
a spawned process with fixed shared-memory transport slots. The backend directory
must not already exist. Neither is a remote create-only publisher or general RL library.

## Bounded writer and actual mjlab capture

CPU-only writer check (same storage environment):

```sh
.venv/bin/python -B check_writer.py
```

It reaches backpressure with one slot and checks exact readback. It then kills
only its own spawned writer, checks failure propagation and verifies that the
published prefix remains readable without a clean completion marker.

GPU runtime pins are in `requirements-capture.txt`; use a separate compatible
Linux/CUDA environment. The measured run reused an existing mjlab environment
with DreamDB in a private import directory; it did not reinstall the training
environment. See [CAPTURE-RUN.md](CAPTURE-RUN.md) for the bounded Slurm command.

Inside a GPU allocation:

```sh
python -B -u check_capture.py
```

This runs 32 Cartpole worlds for 11 control steps, including explicitly configured
termination/time-out paths. Auto-reset capture, manual-reset reference and public
SDK verification run in separate processes. It checks 464 events, then runs
independent state playback and EGL rendering before removing its generated dataset,
reference trace and caches. No policy training is implied. The reference observes pre-reset terminal state through
the public environment boundary; it is not a second recorder-hook implementation.

`DreamDBRecorder` uses the existing mjlab hooks. The owner attaches the writer,
calls `begin_step` with the actual pre-step actor observation and action, flushes
the final partial batch and explicitly finishes the writer. Closing an environment
after an error aborts rather than silently publishing a successful run end.
GPU-to-host copies are currently synchronous and measured as part of later overhead
work; the prototype does not claim zero-copy or asynchronous CUDA transfer.

No production Ref, private dataset, credential, cluster endpoint or raw cluster
log belongs in this example. Initial storage acceptance uses an isolated local
filesystem backend. Cluster execution uses the user's scheduler; never training
on its controller.

## State playback

`playback.py` imports DreamDB, NumPy and MuJoCo, not mjlab or Torch. It opens a
pinned Manifest, retrieves the saved MJB and only the selected episode's state
columns, and restores qpos/qvel, mocap state and simulation time. It calls
`mj_forward`, never `mj_step`: this is state playback, not action resimulation.

For an existing recording with the capture metadata:

```sh
MUJOCO_GL=egl python playback.py render \
  --backend file:///absolute/path/to/backend --manifest MANIFEST_HASH \
  --env 0 --episode 0 --step 2 --output /new/path/frame.ppm

# On a compatible Linux desktop with a display:
python playback.py view \
  --backend file:///absolute/path/to/backend --manifest MANIFEST_HASH \
  --env 0 --episode 0
```

`--step -1` selects reset; nonnegative values select transition step IDs. A new
PPM file is written exclusively (never overwritten). Space plays/pauses; Left/Right
step; Home/End select first/last; digits 0–9 seek across the selected episode.
Timing uses recorded simulation time, not ordinal database anchors. Incomplete
episodes require `--allow-incomplete` and remain labeled incomplete.

To retain the small acceptance capture for manual use, run
`python check_capture.py capture /new/task/directory` **inside a GPU allocation**.
It writes `backend/` and `receipt.json` containing the Manifest. Unlike the default
`all` coordinator, this explicit mode keeps the recording; remove that task
directory when finished. It is the bounded acceptance variation, not a trainer.

MJB loading currently requires the same MuJoCo version, OS and architecture as
capture. These guards do not promise universal asset portability. One selected
episode and scalar-query anchor lists are held in memory; this is not a streaming
viewer for arbitrary-scale recordings. Headless acceptance covers restore/render
and the control methods, not a native desktop window or keyboard delivery.

## Actual PPO and recording cost

`training.py` is a small RSL-RL environment wrapper, not a trainer fork. Attach
the writer before constructing the wrapper (its constructor resets the env),
then hand the wrapper to the normal runner. It caches the returned actor group
and records it with the next action before stepping. The checked envelope has
observation normalization and wrapper action clipping disabled; the actor input
is not an unspecified normalized latent, and action is not actuator force.

The pinned GPU environment additionally uses `rsl-rl-lib==5.4.2`. Within a Slurm
allocation, or via [training.slurm](training.slurm):

```sh
# Original small-publication baseline:
python -B -u check_training.py --batch-rows 64
# One measured batching improvement, including PPO/readback acceptance:
python -B -u check_training.py --batch-rows 512
```

See [TRAINING-RUN.md](TRAINING-RUN.md) for bounds and measurement definitions.
Each command performs three warm, alternating fixed-action off/on pairs, then
two real PPO updates and a separate-process database/rollout comparison. It
cleans its generated data and caches. No external logger or checkpoint upload.

The training adapter defaults to 512-row publications after the bounded comparison;
the benchmark defaults to 64 to preserve the original baseline. Two transport
slots remain bounded (2 MiB total with 512-row batches). More rows can be buffered
before publication: lower publication frequency is a latency/durability-prefix
tradeoff, not free throughput. The synchronous writer and previous capture smoke
keep their original defaults.

Measured fixed-schedule median including drain: **11.62 s → 5.28 s**, versus
approximately **0.036 s without recording**, for only 512 environment steps.
The faster loop alone hides the final drain; do not report it as sustained
low-overhead training. PPO's 512 stored actor inputs/actions/done flags matched
the trainer's own rollout arrays exactly for both batch sizes. This establishes
integration, not convergence, scale, crash recovery or restartable training.

The subsequent core #381 candidate reduced the same 512-row-batch workload's
median recording+drain from **5.31 s to 0.455 s (11.7x)** on the original Slurm
boundary, with PPO exact readback and independent playback passing. This is an
unreleased core fix, not another adapter/layout change. See [FINDINGS.md](FINDINGS.md)
for the pinned wheel, individual runs, memory and limitations; it is not a
sustained-throughput or large-fleet claim.

## Batch episode and simulation-time windows

`windows.py` is a read-only application reference, using released DreamDB 0.0.13
and NumPy. It does not import mjlab, MuJoCo or Torch. The CPU check uses the existing
minimal MuJoCo fixture only to create a valid recorded model asset:

```sh
.venv/bin/python -B check_windows.py
```

Use one pinned reader across calls; build the identity catalogue once:

```python
from windows import EpisodeReader, StepWindow, TimeWindow

reader = EpisodeReader(
    backend, manifest,
    end_anchor=recorded_event_count + 2,  # clean snapshot: run_start + events + run_end
    page_rows=256, max_scan_rows=100_000,
)
batch = reader.read_windows(
    [StepWindow(0, 0, 0, 3), TimeWindow(1, 0, 0.05, 0.15)],
    fields=["obs_t", "action", "reward", "obs_after",
            "next_observation_valid", "terminated", "truncated"],
)
for window in batch.windows:
    for row in window.rows:
        consume(row)  # caller defines collation, masking and training semantics
```

`end_anchor` is an explicit exclusive ordinal bound from your publication receipt;
the formula above applies only to a clean run with a published end marker. Step
windows are half-open and exact; time windows filter recorded simulation time and
can be empty. Neither crosses into another episode. Default reads require complete
episodes; pass `allow_incomplete=True` deliberately for a captured prefix. Missing
next observations stay `None`, not zeros. Repeated requests preserve output order
and return independent arrays.

There is no global random sampler, padding, prefetch pool or Torch DataLoader.
Choose those policies in your own application. The reader reuses its O(prefix
transitions) identity catalogue, coalesces overlapping payload pages per batch,
and reads only explicit fields plus an internal `kind` anchor carrier. It does
not load model bytes for window reads. Scan/request/output-row caps are explicit;
SDK/native metadata and caller-retained arrays are not covered by a total-RSS
guarantee. This is not yet a large-dataset ingestion/replay service.

In the local 88-event fixture, 32 requests return the same 64 output rows while
reducing payload window calls from 32 to 1 (2,848 to 89 rows returned by those
calls). Index setup is measured separately; these are SDK calls, not network GETs.
See [WINDOW-SPEC.md](WINDOW-SPEC.md), [WINDOW-PLAN.md](WINDOW-PLAN.md),
[FINDINGS.md](FINDINGS.md) and [issue #4](https://github.com/dreamlake-ai/dreamdb-examples/issues/4).
