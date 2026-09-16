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

No DreamDB defect has yet been established by this prototype. No application
round-trip, asset portability, training integration or recording performance
claim is marked passed.

## How to report an actual finding

Record: user-facing operation; exact SDK/core and example versions; smallest
reproduction; expected/actual behavior; data or performance impact; classification;
chosen fix or documented limitation; linked change; result of the original check.

Prefer a short runnable reproduction over a large raw log. Adapter mistakes get
fixed here. Generic database bugs, expensive access patterns and unclear API
contracts are legitimate outputs of the prototype, not embarrassments to bypass.
