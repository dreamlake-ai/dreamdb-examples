# mjlab / DreamDB reference prototype

Status: **design milestone; implementation and end-to-end acceptance pending**.
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

No production Ref, private dataset, credential, cluster endpoint or raw cluster
log belongs in this example. Initial storage acceptance uses an isolated local
filesystem backend. Cluster execution uses the user's scheduler; never training
on its controller. There are no runnable implementation commands yet.
