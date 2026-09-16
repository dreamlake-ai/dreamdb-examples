# Reference design

## 1. Small structure, not a framework

Planned modules (not yet implemented):

| Module | Responsibility |
| --- | --- |
| `capture.py` | Cartpole setup, mjlab RecorderTerm hooks, episode bookkeeping |
| `store.py` | Schema, fixed-size capture batches, single writer process, public SDK reads |
| `playback.py` | Open pinned snapshot, select episode, restore saved state, render |
| `run.py` | Small CLI for capture, inspection, playback and performance comparison |

No service, REST API, plugin loader, abstract storage backend hierarchy, package
release train or independent application lifecycle. Keep task-specific code
visibly task-specific. Dependencies belong to this example alone.

## 2. First DreamDB mapping

One fresh Ref/dataset per run; one row per event. The metadata lives in the same
dataset, avoiding an implied cross-Ref transaction. Use ordinary scalar fields:

| Group | Representation |
| --- | --- |
| Identity | integer env/episode/step/sim_step, categorical row kind |
| Physical state | named scalar float components of qpos/qvel and simulation time |
| Transition | scalar observation/action components, reward, boolean flags |
| Optional next observation | validity flag plus components only where present |
| Run metadata | scalar string containing versioned JSON and small model payload |

For Cartpole, scalar components keep exact values and public queryability without
misusing compressed embeddings or image fields for arbitrary tensors. Float32
values can be represented exactly by float64 scalar values; readback still
checks the actual round trip. Dimensions/order are explicit metadata. This
layout may be unsuitable for high-dimensional observations: measure bytes and
object counts before recommending it elsewhere. A missing efficient generic
tensor/record representation would be a DreamDB finding, not something to hide
behind a custom database inside a payload.

Metadata-only rows must not cause unrelated columns to be filled with invented
state; make fields optional where appropriate. `run_start` precedes event rows;
`run_end` follows a successful drain. A playback reader first reads metadata,
then only the selected episode's fields. Do not hydrate every schema field just
to retrieve anchors or identity.

### Public API checkpoints

At DreamDB core revision `7d7c440db3b8c097e995e97003a0c0cd3c837ed5`,
the Python source exposes scalar schema builders, `append_many`, `commit`,
`current_manifest`, `open_by_manifest`, `iter_all_batches` with projection and
range, and `iter_scalar` with equality predicates. These are source observations,
not an assertion that an arbitrary installed wheel matches that revision.

The implementation must pin and exercise its actual wheel. In particular,
`iter_scalar` at this revision lacks a `fields` parameter, while range readers
have one. Evaluate a public-API composition (identity query then projected
windows) and report its cost; do not call private readers to conceal an API gap.
For the small first workload, bounded ranges and explicit projection are enough
to test feasibility; large-dataset scaling remains unproved.

## 3. Capture and bounded writing

Recorder hooks collect tensors into owned capture slabs. Saved policy-input
observations must not alias buffers overwritten by the next step/reset. Reset
and terminal records have separate slots and identities. An observer around the
action loop can supply policy-input observations if the recorder hooks alone
cannot capture them correctly; this must work for the selected PPO wrapper too.

Start with explicit, correct synchronization and measure it. Only introduce
pinned-memory/nonblocking copies if needed, with a CUDA completion event checked
before host encoding or slab reuse. Do not launch speculative CUDA work from
the writer process. Use multiprocessing `spawn`, never fork a live CUDA context.

The writer receives CPU-only bounded batches, encodes rows and calls
`append_many(..., commit=True)` initially. This intentionally bounds hidden
uncommitted accumulation and makes the acknowledgment clear. Batch rows and
bytes, not per-step calls. `commit=False` is not assumed to eliminate memory
cost or provide persistence; use it only for a demonstrated need with a bounded
commit cadence and measured benefit.

The application budget counts filled slabs, queued/in-flight batches and any
serialization copies it owns. It is not a bound on DreamDB/native connector
memory, Torch allocator caches or total RSS; measure those independently. Use
bounded waits that observe writer failure, so backpressure cannot deadlock after
the writer exits. Emit a concise failure, not a retry/orchestration framework.

## 4. Readback and playback

After producer/writer exit, reopen the published Manifest in a different
process. Recover metadata/model from DreamDB, not the source environment or
producer's memory. Select `(env_id, episode_id)`, validate sequence/completion,
and expose incomplete episodes as such. Load only required state columns.

Use saved simulation time for frame timing. Seek by episode step using public
query results; restore qpos/qvel (and supported additional state), call MuJoCo
forward, then render. Export a short video or use a local MuJoCo viewer; neither
requires a web application. Headless frame rendering is the scheduler acceptance
boundary, while pause/step/seek can run on a desktop with the same stored data.

## 5. Explicit limitations and feedback

- Cartpole's native task has a time-out termination only. Normal truncation can
  be exercised by shortening the episode; termination handling needs an explicitly
  labeled test task variation, not a claim that the native task terminates on falls.
- Fixed-model playback excludes domain-randomized model parameters and arbitrary
  terrain/assets. Random reset states remain supported by recording actual state.
- Logical ordinal anchors make ordering unambiguous but require explicit simulation
  time; evaluate this ergonomics tradeoff as a database user.
- Component scalars favor clarity over compact high-dimensional tensor storage.
- Filesystem performance is not S3/network performance. Do not extrapolate.
- Appended data and a database commit do not resume a policy optimizer or RNG state.

Findings should improve ordinary DreamDB users' experience: projected reads,
batch publication, exact values, actionable errors, memory usage and documentation.
Do not predeclare any item a core bug solely because an API signature looks
inconvenient. A real execution or a specific source contract must establish it.
