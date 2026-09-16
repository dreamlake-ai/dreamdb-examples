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

No DreamDB defect has yet been established. Real capture, full playback, training
integration, bounded-writer failure behavior and recording performance remain
unverified. This is a local example check, not a formal testbox verdict for core.

## How to report an actual finding

Record: user-facing operation; exact SDK/core and example versions; smallest
reproduction; expected/actual behavior; data or performance impact; classification;
chosen fix or documented limitation; linked change; result of the original check.

Prefer a short runnable reproduction over a large raw log. Adapter mistakes get
fixed here. Generic database bugs, expensive access patterns and unclear API
contracts are legitimate outputs of the prototype, not embarrassments to bypass.
