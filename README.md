# DreamDB application examples

Reference applications built **on top of** [DreamDB](https://dreamdb.dreamlake.ai).
Use them to learn how to define your own data model, store and query data, and
connect it to an external workflow. This is not a training framework, an SDK
package, or a collection of production-ready products.

## Choose a scenario

| What you want to build | Start here | Scope and status |
|---|---|---|
| Record parallel simulations, inspect episodes and play back physical state | [Simulation recorder and playback](mjlab-reference/README.md) | Validated reference: bounded mjlab capture, playback, PPO integration and window reads; not a large-scale recorder |
| Feed stored images, sensors and actions into training | [Multimodal training reader](multimodal-training/README.md) | Validated reference: real capture/read/train runs; optional performance experiments, not a generic streaming trainer |
| Ingest real egocentric video and measure semantic search and concurrent writes | [Egocentric-100K experiment](egocentric-search/README.md) | Experimental: bounded real S3/Slurm pilot; not a full-corpus or production throughput claim |
| Retrieve scene images by camera pose | [LLFF + DreamDB](llff-dreamdb/README.md) | Legacy/unverified against the current SDK; uses the old `dreamdb_dataset` API |
| Compare that retrieval workflow with another store | [LLFF + LanceDB](llff-lancedb/README.md) | Companion comparison, not a DreamDB application; current dependencies not revalidated |
| Convert local scenes for desktop viewing and comparison | [LLFF + Rerun](llff-rerun/README.md) | Companion: local LLFF → Rerun/LanceDB, no DreamDB reader; current dependencies not revalidated |
| Explore local camera poses in a browser | [LLFF + Vuer](llff-vuer/README.md) | Companion visualization, not a DreamDB storage integration; current dependencies not revalidated |

“Validated” describes the documented checks and environment, not every mode,
scale or deployment. Start with either validated reference to copy the current
application/storage separation. Do not start a new SDK integration by copying
the legacy imports unchanged.

## How to use this repository

1. Choose one application and read its README's dependencies and smallest run.
2. Create an environment for that application only. There is deliberately no
   root dependency bundle: a storage reader need not install a simulator or UI.
3. Read its data contract and design before adapting field meanings or workflow.
4. Follow its output/cleanup instructions. Use your own isolated data directory
   and configuration; cluster scripts are templates, not portable hosted services.

The repository uses Git LFS for some bundled LLFF images/binary assets. Install
Git LFS before fetching those assets; the generated simulation fixtures do not
depend on the LLFF dataset. Shared LLFF helpers live in `llff_utils.py`.

## Application versus DreamDB

The application defines episodes, camera poses, labels, training samples,
transforms and playback behavior. DreamDB supplies storage, snapshots and
queries through public APIs. Users install mjlab, MuJoCo, Torch or visualization
libraries only when their chosen application requires them.

The references also exercise DreamDB as real users and report product issues.
Measured costs and negative findings are part of the examples, not promises
that every workload will obtain the same speedup.

## Experiments and compatibility

[Multimodal experiment index](multimodal-training/EXPERIMENTS.md) separates
on-demand reading, cache/selection experiments and optional prepared formats.
Historical reports keep their exact source/package pins. Core optimizations
can be merged without being present in an example's pinned PyPI package; a
benchmark using private wheels is not a released-package result.

There is currently no repository-wide CI or unified runtime qualification.
Checks live with their applications. Legacy examples were not rerun during the
documentation reorganization.

## Add another application

See [CONTRIBUTING.md](CONTRIBUTING.md), the
[example contract](docs/EXAMPLE-CONTRACT.md) and the
[README template](templates/application/README.md). Other domains are welcome;
new applications should not depend on the robotics examples or become plugins
in a shared framework.
