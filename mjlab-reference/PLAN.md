# Implementation and acceptance plan

Status: bounded D/S/C/P/T milestones completed; reference handoff and measured
performance limitation documented. Changes are tracked in examples issue #2.
This does not establish production-scale suitability or close core follow-up work.

## Milestones

### D — Definition (this change)

- [x] Labeled issue, scope and ownership.
- [x] Application contract and reference design.
- [x] Installed mjlab hook semantics and native Cartpole termination checked.
- [x] Public DreamDB API source checkpoints and known limitations documented.
- [x] Storage runtime pins: dreamdb 0.0.13, MuJoCo 3.11.0, NumPy 2.5.3.

### S — Storage slice, before GPU integration

Completed locally via `check_storage.py` (details in FINDINGS.md).
Pin a released SDK or an explicitly built core revision in an isolated environment.
Write a small two-environment trace using actual scalar and typed-array fields, publish, close
the writer, and reopen by Manifest from a separate process. Check all identity,
flags and numerical values, model bytes and projected episode reads. Include an
incomplete tail and ensure it is not labeled complete. This validates the generic
storage mapping, NOT mjlab hook timing. Resolve a demonstrated SDK gap before
proceeding; record the actual API composition and version.

### C — Real capture and bounded writer

Completed on one Slurm GPU node; see FINDINGS.md. The accepted envelope includes
the scene's mocap state, but no actuator activation state or model randomization.

Implement one RecorderTerm and the small action-loop integration needed to preserve
policy inputs. Use the installed Cartpole task, fixed model, no model DR, initially
32 worlds and short episodes. Add an explicitly labeled variation to reach
termination as well as native time-out; preserve both flag meanings. Run under
Slurm with an explicit resource/time limit and an isolated file backend.

Use a deliberately small queue once to reach backpressure; verify it blocks or
fails explicitly rather than silently losing events. Exercise one real writer
failure, propagate it to producer/close and do not publish a clean run-end marker.
No matrix of synthetic failures or tests of the checker's own machinery.

### P — Independent state playback

Completed under Slurm: eleven selected poses and eleven EGL-rendered frames,
including both end paths and subsequent reset. Pause/step/seek/timed advance and
incomplete-prefix opt-in passed. Native desktop window/key delivery remains
unverified; the viewer calls the checked control methods. See FINDINGS.md.

Stop the capture process. A new process loads model/state from the pinned database
snapshot and reads complete episodes from two environments plus a terminal/reset
boundary. Check restored primary state and derived pose against a small set of
capture-time reference samples. Render selected frames through EGL. Implement
episode selection, pause/step/seek in a simple local viewer; headless checks use
the same state-loading functions. No pixel-identical cross-driver requirement.

### T — Training integration and performance

Completed on Slurm with RSL-RL 5.4.2: two real PPO updates, 512 exact transition
comparisons against trainer rollout arrays, and three paired fixed-action runs
at each of 64/512 rows per publication. One batching improvement gave about 2.2x
with-drain speedup, but recording remains expensive. See FINDINGS.md; stop tuning
this prototype rather than claim the remaining bottleneck is solved.

Run a short actual Cartpole PPO session with the recorder; do not call random
action capture a training test. Confirm the recorder observes the policy input,
terminal handling and batched env step without changing the trainer's rollout
buffer. Do not require learning convergence to validate data recording.

Run an off/on comparison with fixed action schedule for recording overhead, then
report the separate short PPO measurement. Warm JIT first, alternate modes and
take a small fixed number of paired runs (three initially), not unlimited
benchmark tuning. Use fixed task/configuration, environment count, seed, horizon,
recorded env set and storage backend; disclose remaining nondeterminism.

Report env-steps/s, wall time with and without drain, capture/copy and queue-block
time, writer rows/bytes per second, bytes/object counts per simulated second,
queue high-water bytes, RSS and GPU memory. No fixed slowdown promise before
measurement. Optimize the largest measured bottleneck once; continue only if
there is material benefit or a correctness problem. Document unexpected costs
even when they make the chosen mapping look bad.

### F — Product feedback and handoff

Reference handoff: README, ADAPTING.md and FINDINGS.md describe the implementation,
public API composition, measured cost, reproduction and limitations. Core feedback
is a performance investigation, not a demonstrated corruption bug or an RL feature
request. Native desktop interaction and production scale remain unverified.

Each demonstrated DreamDB issue gets a minimal reproducer and a linked core
issue/PR where appropriate. Keep RL-specific changes here. Rerun the same failing
application boundary against a fix; don't replace it with a mock or private read.
Document any unresolved gap rather than declaring a blocked milestone complete.

Finish with the spec, small readable implementation, commands, pinned dependencies,
results, limitations and a short guide to adapting the pattern to another domain.
No separate product roadmap or long-term support promise.

## Minimum evidence by primary claim

| Claim | Reachable failure | Smallest sufficient evidence |
| --- | --- | --- |
| Transition/reset identity is correct | Terminal state replaced by new episode; duplicate/missing step | Real parallel capture spanning reset; check identities, flags, cached observation and sampled states |
| Data survives outside producer memory | Missing/altered values after publication | Separate-process public SDK reopen and complete small-trace comparison |
| Playback uses stored state/assets | Training directory or environment required; wrong pose | New process loads saved model, restores selected states and renders; numerical pose comparison |
| Buffering does not silently lose data | Saturation drops records or writer failure hangs producer | Small bounded queue and one failing writer at the actual application boundary |
| Recording cost is characterized | Fast producer hides indefinitely growing queue/drain | Paired real workload with final drain, queue and memory measurements |
| A DreamDB fix helps this consumer | Fix passes unit test but reference workload still fails | Original application reproducer against the fixed SDK |

Structural ownership/synchronization constraints are checked in source, not by
inventing runtime seams. These checks do not validate other validators. Stop
expanding evidence once the stated reachable claim is directly checked.

## Execution discipline

- No existing user environment changes; new dependencies go in a task-specific env.
- No jobs on the scheduler controller, no direct compute-node SSH, no cluster tuning.
- Before GPU work, publish the exact command, workload bounds and timeout in the run plan.
- Local checks first. Use the existing testbox workflow for formal DreamDB-core
  verdicts when a core change is required; CI is for a substantive PR/key change,
  not each experiment. Do not build a new testbox for this example.
- Do not upload private data, credentials, raw diagnostic archives or model assets
  without checking their provenance/license. Keep synthetic example outputs small.
- Remove task scratch data, environments, redundant logs and build directories at
  completion. Preserve source changes durably before removing a worktree.
