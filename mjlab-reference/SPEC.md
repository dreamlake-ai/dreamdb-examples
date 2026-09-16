# Application contract: parallel recording and state playback

Status: v0 application contract; storage slice implemented, capture/playback
pending. This is not a DreamDB protocol specification. Requirements for unfinished
milestones remain acceptance targets, not claims that they already work.

## 1. Ownership and supported envelope

| Concern | Owner |
| --- | --- |
| Episode, environment, step, termination, policy identity | Example application |
| Capture timing, action/observation interpretation, simulation assets | mjlab adapter |
| Generic fields, content storage, snapshot publication, reads | DreamDB |
| State-to-scene reconstruction and presentation | Playback application |

First envelope: one process driving one GPU, fixed-model Cartpole with N parallel
worlds, one writer, one new dataset per run. Begin with N=32, not a capacity
promise. Select a fixed set of recorded environments before running. Do not
silently sample away transitions within a selected episode.

Excluded: distributed training/replay services, live policy serving, restartable
training checkpoints, arbitrary robot assets, per-world model randomization,
general tensor formats, deterministic action resimulation and multi-writer runs.
Unsupported task/model variations must be refused or explicitly outside this
example, not silently accepted under a general playback guarantee.

## 2. Identity and clocks

- `run_id`: fresh application identifier; a run must not reuse an existing Ref.
- `(run_id, env_id, episode_id)`: episode identity. Episode counters are per env.
- `step_id`: zero-based transition number within an episode.
- `sim_step`: global application control-step counter, distinct from physics
  substeps and episode step. Store control timestep and decimation in metadata.
- DreamDB `_anchor`: unique monotonically increasing **logical record ordinal**,
  allocated by the recorder. It occupies the database's nanosecond coordinate
  namespace but is NOT wall time or physical simulation time. Metadata declares
  `anchor_encoding=logical-record-ordinal-v1`. Refuse signed-window overflow.

Multiple environments at the same simulation time must never collide. Episode
selection uses explicit scalar identity, not assumptions about contiguous time
ranges. Playback timing comes from simulation time/control timestep, never from
differences between synthetic anchors. This deliberate mapping is a prototype
tradeoff to evaluate, not a recommended universal temporal model.

## 3. Event semantics

There are four row kinds: `run_start`, `reset`, `transition`, `run_end`.
Metadata rows have no episode identity. Data rows have explicit identity.

`reset` records the initial physical state and observation for a new episode,
before its first action. A `transition` records:

- the observation supplied to the policy, `obs_t`;
- the action supplied to the environment, `action_t` (not a claim about actuator
  force after clipping/scaling);
- reward, `terminated`, `truncated` returned for that action;
- physical state after the action and before any reset, `state_after`;
- `next_observation_valid` and, when valid, `obs_after`.

Both termination flags may be true; preserve them separately. Never synthesize
one by negating the other. A workload stopped by a capture limit has an
incomplete episode, NOT an invented timeout transition.

### Actual mjlab 1.6.0 auto-reset contract

The installed source calls `record_pre_reset` before reset, `record_post_reset`
after fresh observations, and `record_post_step` for all envs afterward.

| Capture point | Record |
| --- | --- |
| Initial `record_post_reset` | New episode's reset state and initial observation |
| `record_pre_reset(ids)` | Old episode's terminal transition and physical state |
| Auto-reset `record_post_reset(ids)` | New episode's reset row, new identity |
| `record_post_step`, excluding reset envs | Continuing transition and new observation |

At pre-reset, `obs_buf` is the preceding observation, NOT the post-action
terminal observation. The latter is not computed by the normal auto-reset
path. Record `next_observation_valid=false` there; do not pretend reset's
observation is a terminal observation. Non-reset transitions use the cached
policy-input observation and the fresh post-step observation. Snapshot values
before mjlab mutates their underlying buffers. A terminal transition is emitted
exactly once, never again in post-step.

Primary `qpos/qvel` may be captured before forward kinematics refresh; derived
`xpos` etc. can lag one physics substep. V0 records primary state and reconstructs
derived geometry during playback; it does not claim that captured derived
quantities are terminal-state-correct.

Manual resets after initialization and restoring training checkpoints are out
of scope for v0. Adding them requires explicit episode-end semantics first.

## 4. Exact state and assets

For the chosen fixed-model task, persist all qpos/qvel components, simulation
time and the observed/action values without lossy vector compression. Store
actuator state or mocap values if present; initially require zero dimensions for
unsupported state families. Physical state is not a similarity embedding.

Store the compiled model and metadata through DreamDB, not a training-machine
path. V0 uses a `u8` typed array containing the MuJoCo MJB in the run-start row,
with digest and byte length in metadata. State/observation/action fields use
fixed-shape `f32` typed arrays, little-endian, C layout, raw codec. No base64,
compressed embeddings or custom array decoding is necessary: the released Python
SDK has a public typed-array API. Pin MuJoCo version/platform compatibility, joint
order, dimensions, task configuration, library versions and example revision.
Verify the saved model loads in the independent playback process. No model
parameter changes after the captured model are supported in v0.

Playback restores a reset/transition's primary state in the saved model, runs
forward kinematics and renders; it does not integrate the recorded action.
Episode selection, stepping, pause and seeking are presentation controls, not
new database semantics. Reconstructed poses are checked numerically; pixel
identity across graphics drivers is not promised.

## 5. Publication and failure

One writer owns the dataset. Queue acceptance and successful GPU-to-host copy
are NOT persistence acknowledgments. Only a successful DreamDB publication
advances the recorded durable prefix. Reads pin a published Manifest so later
appends do not change a playback session underneath it.

An episode is complete only when the pinned snapshot contains its reset row,
contiguous transitions and terminal/truncated transition. Missing tails stay
incomplete. A clean `run_end` is published only after all captured rows drain;
it records final counts. It does not retroactively complete live episodes cut
off by the run limit. After a crash, no clean run-end marker means interrupted;
do not promise recovery of queued/uncommitted rows or automatic resume.

The recorder is bounded by a declared byte budget, fixed slab count and maximum
row/batch size. Full buffers apply explicit backpressure. No silent eviction.
Writer errors reach the producer/close operation and suppress clean completion.
No automatic retry of an ambiguous commit in v0; surface it for inspection
rather than risk duplicate logical events.

## 6. Performance claims

No database calls or per-environment publication in the simulation hot path.
Batch multiple steps/environments; keep the training rollout buffer unchanged.
Measure capture/copy time, producer blocking, writer throughput, queue byte
high-water mark, wall time including final drain, host memory and GPU memory.
Report startup/JIT separately. Asynchronous submission alone is not proof of
asynchronous CUDA transfer or improved end-to-end throughput.

Compare the same task/config/seed/action schedule with recording off/on. A
capture-only action driver establishes simulation-recording overhead, not PPO
training throughput. A short PPO run is a separate final integration check;
neither demonstrates policy convergence or large-cluster capacity.

## 7. DreamDB-as-user feedback obligation

Use public Python SDK calls and normal readers. Do not manipulate manifests,
parse private object layouts or patch mjlab/DreamDB to make the example pass.
A reachable failure is recorded with pinned versions, a minimal application
reproduction, expected behavior, actual behavior and impact.

Classify findings as adapter errors, existing-API misuse/documentation gaps,
generic DreamDB defects/capability gaps, or measured performance bottlenecks.
Fix the appropriate layer; do not move episode semantics into the database.
If a core fix is needed, link a focused core issue/PR and rerun the original
failing application check on the fixed revision. The prototype remains the
consumer, not a replacement engine-test framework.
