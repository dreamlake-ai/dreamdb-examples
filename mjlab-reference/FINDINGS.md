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
validated. Playback was subsequently checked below; PPO training remains pending.
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

## How to report an actual finding

Record: user-facing operation; exact SDK/core and example versions; smallest
reproduction; expected/actual behavior; data or performance impact; classification;
chosen fix or documented limitation; linked change; result of the original check.

Prefer a short runnable reproduction over a large raw log. Adapter mistakes get
fixed here. Generic database bugs, expensive access patterns and unclear API
contracts are legitimate outputs of the prototype, not embarrassments to bypass.
