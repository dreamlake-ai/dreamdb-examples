# mjlab / DreamDB reference prototype

Status: **design and public-SDK storage slice complete; mjlab capture and playback pending**.
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

`store.py` is currently a synchronous local-filesystem primitive, not the future
bounded asynchronous recorder. It refuses an existing backend directory. It
must not be presented as a remote create-only publisher or a general RL library.

No production Ref, private dataset, credential, cluster endpoint or raw cluster
log belongs in this example. Initial storage acceptance uses an isolated local
filesystem backend. Cluster execution uses the user's scheduler; never training
on its controller. Real capture/playback commands will be added in their milestones.
