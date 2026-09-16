# Evidence and DreamDB feedback

This ledger distinguishes observations from proposed improvements. It is not a
new audit framework. Add entries only for a demonstrated application-facing issue
or a result needed to interpret the prototype.

## Existing readiness evidence (not prototype acceptance)

A 27-second, single-GPU Slurm batch diagnostic completed with exit 0:

- RTX PRO 6000 Blackwell Max-Q, 97,887 MiB reported VRAM, driver 590.48.01.
- Python 3.12.3, PyTorch 2.9.1+cu128; CUDA matrix operation passed.
- mjlab 1.6.0 imported successfully.
- MuJoCo-Warp advanced 32 tiny worlds four steps; finite state and simulation
  time 0.008 s checked.
- EGL rendered a non-uniform 64x64 RGB image.

No training, DreamDB write/read or state playback was exercised. This is one
node, not a cluster capacity result. All task caches/logs were cleaned afterward.

## Installed mjlab source anchors

Package version alone is not a proof of pristine upstream source. These are the
SHA-256 digests of the installed files inspected for the design:

| Relative file in mjlab | SHA-256 |
| --- | --- |
| `envs/manager_based_rl_env.py` | `e05034969baaa6ca38d7587190eef95d468fd413f182edd2c8d387c2950701f1` |
| `managers/recorder_manager.py` | `9c30862b75b2c2a77b49f331125be382912099147c6ae982aa682a58ce7c3e66` |
| `tasks/cartpole/cartpole_env_cfg.py` | `f37800dc7d21a22d2d8a6091958b07566000b0cbc9d6073b34531f94e52f4c35` |

Relevant observations: recorder hooks distinguish pre/post reset; terminal
observations are not computed under auto-reset; native Cartpole only declares
time-out termination. Implementation must record the actual files/versions it
runs against; matching package names is not enough to transfer these findings.

## DreamDB API checkpoint — potential ergonomics question, not a filed bug

Source inspected at core `7d7c440db3b8c097e995e97003a0c0cd3c837ed5`:
`dreamdb-dataset-python/src/lib.rs` and `python/dreamdb/__init__.py`.

Scalar equality iteration and projected range iteration are exposed separately;
`iter_scalar` does not expose a projection argument at this revision. The planned
consumer needs episode selection plus a small state projection. Milestone S will
exercise public composition and record its cost before proposing any change.

## Storage slice — released SDK, independent processes

Local execution: Python 3.12.13 on macOS arm64, `dreamdb==0.0.13`,
`mujoco==3.11.0`, `numpy==2.5.3`, isolated environment, file backend. The coordinator
waited for writer exit before launching the reader. Source: `check_storage.py`.

| Primary check | Observed result |
| --- | --- |
| Interleaved data survives independent reopen | 11/11 event rows exact, including identities, flags, sparse field absence and scalar float bits |
| Typed arrays retain physical values | All dtype/shape/byte comparisons passed, including float32 negative zero |
| Episode classification | Three complete; a continuing episode and reset-only episode remain incomplete despite clean run_end |
| Projected episode retrieval | Public scalar lookup + bounded projected windows returned exactly the selected qpos values, with no other field materialization in the returned batches |
| Snapshot pinning | Earlier published prefix retained four original events, no clean run_end, incomplete episode, despite subsequent publication |
| Saved model is usable outside producer | 4,588 bytes recovered from a u8 array, length/hash matched, loaded as a 2-DOF MJB in the reader |

The complete event read took 14.057 ms in the first execution. This is one tiny
local run, not a throughput benchmark, network measurement or scaling claim.
Only same-platform/same-MuJoCo-version asset loading is established. Synthetic
records test storage, not actual mjlab callback timing. No renderer was used.
The prior prefix check is not a crashed-writer test; failure propagation belongs
to the bounded-writer milestone. All generated storage was removed automatically.

### Design correction, not a DreamDB gap

The draft overlooked the released `Schema.add_array`/ndarray read support and
proposed scalar components/base64. Runtime API inspection and the round trip
confirmed exact f32/u8 arrays are already supported. The implementation and
contract now use them; no engine change or new core issue is justified here.

The projected scalar-filter composition works for this small input. It does
materialize two anchor lists and can fetch neighboring env records in each
bounded window. Whether a combined filtered/projection API materially improves
this workload remains a measurement question, not an established engine defect.

No DreamDB defect was established by the storage slice. Its result is a local
example check, not a formal testbox verdict for core.

## Real mjlab capture and bounded writer

The successful Slurm job completed in 34 seconds, exit 0, on one RTX PRO 6000
Blackwell GPU. It requested four CPUs but the site's select/linear allocation
reserved the 32-CPU node. The task configuration and command were defined in
CAPTURE-RUN.md before submission. No training or production storage was involved.

The existing runtime was not modified: DreamDB 0.0.13 was loaded from a temporary
import directory, alongside mjlab 1.6.0, Torch 2.9.1+cu128, MuJoCo(-Warp) 3.11.0,
Warp 1.14.0 and NumPy 2.5.3. Runtime pins describe this tested combination, not
a claim that all upstream packages/files have an independently verified origin.

| Primary check | Observed result |
| --- | --- |
| Real parallel capture | 32 environments, 11 steps, 352 transitions + 112 reset events = 464 event rows |
| Distinct end/reset paths | 48 terminations, 32 time-outs; 80 complete episodes and 32 incomplete tails |
| Independent reference | Auto-reset capture compared with separate manual-reset env.step/reset execution; event identity/fields/flags equal, maximum array difference 0.0 (check tolerance rtol=1e-5, atol=1e-6) |
| Extra scene state | All mocap positions/quaternions captured and compared, as well as qpos/qvel, observations, actions, rewards and simulation time |
| Bounded transport | One 131,072-byte shared slot; encoded in-flight high-water 21,519 bytes; 7 backpressure waits totaling 3.3877 s |
| No silent loss under pressure | All 464 submitted events matched the reference after independent public-SDK reopening |
| Writer death | CPU check killed only its own writer after a known published prefix; caller received failure, prefix stayed readable, run_end absent |
| Cleanup | Coordinator removed generated dataset/reference/cache; scheduler reported COMPLETED and released the node |

The CPU writer check ran on macOS and on the allocated Linux node: 11/11 rows
matched under a one-slot queue, and both runs reached backpressure. Killing the
child is a real worker-liveness failure; it does not establish recovery from
every connector error or an ambiguous commit. No retry guarantee is made.

### Corrected application assumption: Cartpole has a mocap body

Two initial short executions stopped at the fixed-model capability check. The
second printed the exact trigger: `na=0, nmocap=1, expanded_fields=[]`. Rejecting
all mocap state would make even this selected task unsupported. The schema and
recorder now preserve its position/quaternion using ordinary f32 typed arrays;
the successful run compared those values too. The guard still rejects nonzero
actuator activation state and expanded model fields. This was an adapter-envelope
correction, not a DreamDB defect; no guard was simply removed to make the run pass.

### Performance boundary

3.3877 s of actual producer blocking is a useful cost signal, not an off/on
training slowdown measurement. The 34 s job includes cold compilation, CPU writer
checks, two simulation processes and a reader. The 128 KiB arena is not a bound
on total host/GPU memory: decoded Python values, source arrays, one serialization,
model startup and SDK/connector allocations are additional. Full throughput/RSS
comparisons remain milestone T; no network or cluster-scale result is inferred.

No core defect was demonstrated. The actual actor-observation capture is checked
for this fixed action driver; PPO normalization/wrapper integration is not yet
validated by that capture run. Playback and actual PPO were subsequently checked below.
Raw traces, models and large logs are not archived in this repository.

## Independent state playback

The subsequent Slurm run completed in 35 seconds, exit 0, on the same GPU/runtime
envelope. This includes writer checks, capture, independent manual-reset reference,
database verification and a fourth process for playback; it is not playback-only
latency or a performance comparison. No mjlab/Torch import is needed by the player.

Primary claim: the selected episode can be reconstructed and rendered after the
producer exits, using only its database-persisted model and primary state. The
reachable failure is missing/wrong assets or state producing a different pose.
The minimum evidence is the separate-process restore and real EGL rendering;
no additional validator/mutation framework was added.

| Check | Result |
| --- | --- |
| Capture repeated with playback metadata | 464 events; independent reference maximum array difference 0.0 |
| Pinned database model | MJB loaded from run-start typed array; digest/length and MuJoCo/platform checked |
| Primary state | qpos/qvel and mocap position/quaternion exactly matched stored f32 values after restoration |
| Selected pose reference | 11 samples from two environments, complete first episodes, termination/time-out and subsequent reset; maximum body xpos/xmat difference 0.0 (rtol=1e-5, atol=1e-6) |
| Actual renderer | 11 nonuniform 320x240 RGB frames, all with different hashes; no cross-driver pixel-equality claim |
| Controls | Pause, backward step, step-ID seek, simulation-time advance and end pause passed through the same methods used by the viewer |
| Incomplete tail | Refused by default; explicitly allowed and still labeled incomplete |
| Native desktop window/key delivery | Not tested on the headless node |

The reference computes kinematics from the independent simulation's original
model and primary state. It does not compare stale GPU-derived xpos, which can
lag integration, and does not mutate the simulation to refresh it. The player
independently loads the database model/state and calls mj_forward, never mj_step.
This checks stored-state reconstruction, not MuJoCo's kinematics implementation
or deterministic action resimulation.

An initial job stopped before simulation because the task staging omitted
`check_storage.py`, imported by the writer check. Copying that existing dependency
fixed the staging error; the next job passed. This was not a product defect and
did not require another validation layer.

Local storage round-trip, writer pressure/death checks, CLI help, Ruff and shell
syntax also passed. Native viewer integration, large-episode memory/query cost,
PPO behavior and off/on overhead remain outside this result. No DreamDB-core
change or defect was established. Generated databases, reference poses, frames
and per-job compilation caches were temporary; retain only code and these concise
results, not raw traces or model assets.

## Real PPO and bounded recording-cost experiment

RSL-RL 5.4.2, same mjlab/Torch/MuJoCo environment above. Two Slurm jobs completed
with exit 0 (77 s baseline and 51 s larger-batch experiment), including cold startup,
all comparison runs and independent verification. No external logging/checkpoint
upload. An initial submission was rejected because staging had not finished;
waiting for the copy and resubmitting fixed this orchestration error before any job.

### Actual training integration

The normal MjlabOnPolicyRunner/PPO performed two updates, eight steps each across
32 worlds, with 32x32 actor/critic MLPs and two epochs/two minibatches. The original
optimizer and rollout implementation were not modified. Actor parameters changed
and remained finite; this is not a convergence result.

The checker reads the actual rollout's observations/actions/done arrays after
each update. RSL-RL 5.4.2 `RolloutStorage.clear()` only resets its cursor, leaving
those values available; the checker does not mutate storage. After producer exit,
an independent DreamDB reader compared all **512 transitions exactly**, including
step/environment identities. There were 144 complete episodes and 32 incomplete
tails, with both termination and time-out reached. Both batch sizes passed.

| PPO recording | Learn calls (s) | Final flush/drain (s) | Sum (s) | Rows / append publications |
| --- | ---: | ---: | ---: | ---: |
| 64 rows/batch | 5.1734 | 6.6863 | 11.8597 | 688 / 11 |
| 512 rows/batch | 0.2343 | 5.3130 | 5.5473 | 688 / 2 |

These are separate short runs, not a PPO on/off comparison. Setup, witness-array
copies between learn calls and subsequent verification are excluded from the sum.
Model observation normalization and wrapper action clipping are disabled. Recorded
reward remains environment reward, not PPO's time-out-bootstrapped reward. The
adapter caches the actor group returned to the runner before its next step.

### Fixed-action performance, including drain

One full unrecorded warm-up per process, then three pairs in off/on, on/off,
off/on order. Each run resets 32 worlds at seed 71 and executes the same 16-step
schedule: 512 environment steps, 688 recorded events, 25.6 aggregate simulated
environment-seconds. Both modes auto-reset. Startup/model/header are outside the
timed reset+loop+drain; setup was 0.022–0.036 s off and 0.122–0.129 s on.

| Batch rows | Pair | Off, with drain (s) | On loop only (s) | On, with drain (s) |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 1 | 0.036129 | 4.949041 | 11.592853 |
| 64 | 2 | 0.035697 | 5.202507 | 12.277567 |
| 64 | 3 | 0.035582 | 4.928214 | 11.621968 |
| 512 | 1 | 0.046186 | 0.046144 | 5.268609 |
| 512 | 2 | 0.035872 | 0.047386 | 5.362855 |
| 512 | 3 | 0.035852 | 0.046720 | 5.276203 |

The one change was publication batching, 64 → 512 rows (two transport slots
remain; total arena 256 KiB → 2 MiB). Median recording+drain improved **2.20x**,
11.62 → 5.28 s. No values were omitted. More rows can remain buffered before
acknowledgment. The optimized two slots fit this entire small burst: zero queue
wait does **not** establish sustained low-overhead recording. Most work moves to
final drain. No further tuning sweep was run.

| Fixed-schedule measurement | 64 rows/batch | 512 rows/batch |
| --- | ---: | ---: |
| Environment steps/s, including drain | 41.70–44.17 | 95.47–97.18 |
| Child append/commit time, s | 11.564–12.224 | 5.215–5.308 |
| Submitted rows / append second | 56.28–59.49 | 129.63–131.93 |
| Inclusive capture callbacks, s | 4.889–5.164 | 0.00918–0.00942 |
| Synchronous host-copy time, s | 0.00304–0.00316 | 0.00291–0.00299 |
| Queue waits / seconds (including final submit) | 9 / 6.860–7.259 | 0 / 0 |
| Encoded in-flight high-water, bytes | 40,194 | 215,682 |
| Backend files, including metadata/history | 6,764 | 6,386 |
| Backend bytes | 2,979,806 | 1,151,640 |
| Files / simulated environment-second | 264.22 | 249.45 |
| Bytes / simulated environment-second | 116,399 | 44,986 |
| Backend bytes / measured wall second | 242,703–257,038 | 214,744–218,585 |

Capture callbacks include their copy/packing/queue waits; the categories overlap
and must not be summed. Final flush is outside callback time. Child append timing
includes normalization/validation and SDK append+commit, not just disk I/O. Backend
bytes count all generated files including metadata/history; this is not useful
payload throughput or a count of unique protocol objects. We did not profile
the internals enough to attribute all the cost to a particular syscall/connector.

Producer sampled RSS across fixed runs was 2.15–2.18 GB; writer peak samples were
48.1–48.7 MB at 64 rows, 50.7–50.9 MB at 512 rows. These are decimal bytes rounded,
sampled every 50 ms, not exact peaks; producer caches persist between pairs. PPO
producer samples reached 2.41–2.42 GB. Torch peak allocated/reserved during PPO
was 18,369,536 / 25,165,824 bytes; fixed runs used at most 134,656 allocated and
4,194,304 reserved. Torch counters exclude Warp/graphics/driver allocations and
must not be presented as total GPU memory. Separate RSS peaks are not simultaneous.

### Product feedback / limit

Tracked as [dreamdb-core #381](https://github.com/dreamlake-ai/dreamdb-core/issues/381)
with `performance` and `priority-medium` labels, pinned reproduction and the
measurement boundary. It is not marked as a proven correctness bug.

The lossless public API works, but this per-event mapping with default unbucketed
small typed arrays and frequent scalar/Track publications is **not a recommended
large-scale robot-RL recorder**. The measured append path dominates while CPU
copies are negligible in this small workload. Larger publication batches help,
yet thousands of backend files and approximately five seconds of drain remain
for less than a second of per-environment simulation.

This is a reproducible generic storage/API performance investigation, not proof
of a corruption bug or proof that every supported array layout is slow. No hot
path bypass, custom database format, training semantics in core, sampling away
events or speculative connector patch was introduced. Next investigation should
identify a supported efficient small-array/scalar ingestion layout and profile
the original append workload, preserving exact values, projected reads and bounded
publication. Do not infer S3 or long-running/large-fleet behavior from these runs.

Temporary datasets, rollout witnesses, JIT caches and task-private imports were
removed after recording these results. The application staging race is recorded
once; no staging-validator framework was added.

## Core #381 consumer feedback loop (2026-09-16)

The prototype exposed a generic ordered-scalar cost, not an RL-specific need:
incremental B-tree insertion encoded every prefix of a fitting page for every
new value. The candidate tries the full page first and retains the existing
split scan on overflow. No adapter/data-layout changes or private APIs.

Core source `5aa915a` (product patch `2587849`, scoped testbox subject `f567bd5`),
unchanged prototype `b0aaf17`. Testbox passed existing scalar page pruning,
sibling reuse, root split and failed-publication behavior (five tests), fmt and
scoped clippy. No new mutation framework. Linux candidate built with Rust 1.98.1,
maturin 1.14.1; wheel SHA256
`04ebb6c3d216e47a961fd4babac1cbb515b60ae9291b51a1e80906eb073998f8`.
It still labels itself 0.0.13 but is **not a published package**. Compare explicit
wheel/import paths, not the version string alone.

Slurm jobs 147373 (CPU build, 3m13s) and 147374 (one GPU, 1m51s) exited 0.
Same node031/RTX PRO 6000, driver 590.48.01 and installed versions above. Within
one allocation the released wheel and candidate each ran the unchanged three
alternating off/on pairs at batch_rows=512, followed by two real PPO updates.
The candidate additionally ran the existing storage/writer and capture/playback
checks. Released and candidate wheels are not compiler-identical builds.

| Measurement | Released 0.0.13 | Candidate |
|---|---|---|
| Complete recording + drain, three runs (s) | 5.31916 / 5.31032 / 5.22361 | 0.50458 / 0.43628 / 0.45507 |
| Recording off, three runs (s) | 0.03621 / 0.03579 / 0.03578 | 0.04631 / 0.03572 / 0.03570 |
| Child append, three runs (s) | 5.23555 / 5.22690 / 5.16859 | 0.45031 / 0.37823 / 0.40021 |
| Backend files / bytes | 6,386 / 1,151,640 | 6,386 / 1,151,475 |
| Maximum sampled writer RSS across three runs (MiB) | 48.42 | 46.19 |
| PPO learn / final drain (s) | 0.22139 / 5.14595 | 0.23085 / 0.39408 |
| PPO sampled producer / writer RSS (MiB) | 2295.86 / 48.08 | 2338.34 / 45.65 |

Median complete recording time improves **11.7x**, without dropping the 688 events
or reducing the two publications / 2 MiB transport arena. Zero queue wait is still
only a short burst result, not sustained throughput. No file-count reduction;
byte totals include metadata/history and are not the exact-payload oracle.

Both PPO runs passed exact comparison of all 512 actor inputs/actions/done flags
to the actual rollout, with finite changed actor parameters. Candidate capture
passed 464 events / 352 transitions, max array difference 0.0. Independent playback
passed 11 pose samples / 11 distinct rendered frames, max pose error 0.0, plus
pause/step/seek/timed advance and incomplete-prefix opt-in. Native window delivery,
large fleets, remote storage, sustained throughput and convergence remain untested.

One build-tool error: `uv` was absent on the worker; the first job stopped before
compilation and its waiting dependent job was cancelled. Task-private installation
through existing pip fixed it without changing the shared runtime. No test changes
or additional validation layers. Generated backends/caches were removed by the
coordinators; task staging/build artifacts are cleaned after retaining these
conclusions and pinned reproduction information.

Reproduce: build the pinned core's Python wheel with `maturin build --release
--locked`, install it into a separate import directory, then run the existing
`check_training.py --batch-rows 512` for each wheel and `check_storage.py`,
`check_writer.py`, `check_capture.py` for the candidate inside the bounded Slurm
allocation. Stop tuning at this material result; remaining array/file overhead
is not claimed fixed. Follow [core #381](https://github.com/dreamlake-ai/dreamdb-core/issues/381)
for review/merge/release, rather than assuming users already have the fix.

## Episode-window read prototype (2026-09-16)

[Issue #4](https://github.com/dreamlake-ai/dreamdb-examples/issues/4) starts with
the public APIs already present in released `dreamdb==0.0.13`; no new core API
or dependency on the unreleased #381 fix. Python 3.12.13/macOS, NumPy 2.5.3,
MuJoCo 3.11.0 for the existing minimal model fixture. The reader itself needs
only DreamDB/NumPy and application semantics. This is a direct local SDK check,
not a core testbox or GPU/training verdict.

`check_windows.py` uses eight interleaved copies of the existing 11-event storage
fixture (88 events), a real minimal model, and the public writer. The reader
reopens a pinned Manifest; a later append completes an old incomplete episode in
a new snapshot, but cannot alter old window results. Exact anchors, ordering,
scalar values, ndarray dtype/shape/bytes and absent next observations pass for
step/time/duplicate/overlapping requests. Incomplete episodes require opt-in,
missing steps are refused, and overlapping output arrays do not alias. A later
reader sees the newly completed episode. No playback/trainer code was changed.

Projection is observed at the actual SDK call boundary: index reads contain
identity/clock/flags plus the initial metadata read, no model/array payload.
Payload reads contain the requested fields plus `kind`, necessary to preserve
terminal rows under an optional-only projection. Three distinct 32-ordinal
pages are fetched once each for the mixed overlap scenario. There is no second
framework to validate these counters.

Separate comparison uses 32 requests (16 episodes twice, two transitions each),
same fields and 256-ordinal page size as existing `read_episode`. All 64 output
rows are compared to input in both paths. One local run, not a timing threshold:

| Work | Existing episode reader | Batched reader |
|---|---:|---:|
| One-time catalogue construction | none | 10.34 ms |
| Payload/selection call elapsed | 637.15 ms | 18.41 ms |
| Scalar-query calls during requests | 64 | 0 |
| Projected window calls during requests | 32 | 1 |
| Rows returned by payload window calls | 2,848 | 89 |
| Output rows, including requested repetitions | 64 | 64 |

The initial 32-row-page catalogue took 20.33 ms / four calls; it is separate
from the 256-row-page comparison above. File cache state is uncontrolled and
the fixture was freshly written: "index construction" does not mean cold disk
cache. Counters include actual public calls and returned rows, not physical
object GETs, network bytes or total memory. The catalogue has an explicit prefix
cap and still grows with indexed transitions. Batch payload memory also depends
on field dimensions; native Track/index memory is not bounded by `page_rows`.
This validates the overlap-saving mechanism, not large-corpus or S3 throughput.

No new core deficiency was demonstrated by this slice. Future generic bounded
selection/paging work must establish its own reachable need, rather than adding
RL concepts to DreamDB or treating the prototype as a new database reader stack.
Temporary models/backends are cleaned by the check; only source, conclusions and
the reproduction command are retained. Ruff check/format pass for the new modules.

## How to report an actual finding

Record: user-facing operation; exact SDK/core and example versions; smallest
reproduction; expected/actual behavior; data or performance impact; classification;
chosen fix or documented limitation; linked change; result of the original check.

Prefer a short runnable reproduction over a large raw log. Adapter mistakes get
fixed here. Generic database bugs, expensive access patterns and unclear API
contracts are legitimate outputs of the prototype, not embarrassments to bypass.
