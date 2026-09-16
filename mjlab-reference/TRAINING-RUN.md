# Bounded training/performance run plan

## Episode-window integration follow-up

Issue #4 / PR #5: the new claim is that the window reader can consume actual
multi-environment PPO recordings, not only the synthetic storage fixture. Run
`check_training.py integration --batch-rows 512` inside one bounded Slurm GPU
allocation. This runs only two PPO updates and a separate verification process;
it does not repeat the fixed-action performance sweep. Use released DreamDB
0.0.13 in a private import directory, without changing the shared environment.

After the trainer exits, form step and simulation-time windows for all recorded
episodes containing transitions (including explicit incomplete-prefix opt-in).
Read requests in bounded batches and compare every returned actor input/action/
done directly with the actual rollout arrays, using recorded simulation-step and
environment identities. Also compare anchor order and individual terminal flags
with the existing full-record read. Any wrong episode, missing/reordered row or
changed payload fails the check. This is the minimum real integration boundary;
no new oracle framework, playback rerun or throughput benchmark is required.
Report counts and read-call elapsed time without a production speed claim.

## Original training/performance slice

Written before submission. Same isolated local backend and fixed-model Cartpole
variation as CAPTURE-RUN.md; 32 parallel worlds, seed 71, noise off, even worlds
terminate after three steps, all time out after four. Not native task convergence.
One Slurm GPU, four requested CPUs, 16 GiB, ten-minute limit. Existing environment
is read-only; DreamDB imports from a task-private directory. No external logging,
checkpoint upload, S3, production Ref writes, direct worker SSH or controller training.

Primary claims and minimum checks:

- Real PPO uses the recording adapter: run two actual PPO updates (eight steps
  per rollout, 512 total transitions), 32x32 MLPs, two learning epochs/two mini
  batches. Require finite, changed actor parameters. Reopen DreamDB independently
  and compare every transition's actor input, action and done flag against the
  trainer's own rollout arrays, read without modification after each update.
  No extra trainer validator; no policy-learning/convergence promise.
- Fixed-action recording cost: one full unrecorded warm-up, then three paired
  16-step off/on runs in alternating order (off/on, on/off, off/on). Same config,
  seed, action schedule, process and backend class. Both modes auto-reset.
  Capture all worlds/events; two shared slots, at most 64 rows per publication.
  Startup/model/header time separate from reset+loop and final drain. Cold writer
  startup is excluded from loop but reported; residual GPU nondeterminism remains.

Observation normalization and wrapper action clipping are disabled. The recorded
observation is the actor group's model input, not an unspecified normalized latent;
action is what enters the environment action manager, not applied actuator force.
Runner rollout/optimizer code is not patched. Only the environment wrapper is adapted.

Report per-run wall time with/without final drain, env-steps/s, inclusive capture
callback and synchronous copy time, producer queue wait, child append/commit time,
rows per append second, backend file count/bytes and their per-simulated-env-second
rates. Backend files include metadata/history, not just logical data objects.
RSS is sampled every 50 ms for producer and writer separately (not an exact peak,
and separate peaks cannot be summed into a simultaneous total). Torch peak allocated
and reserved bytes are not total device/process VRAM. Fixed-schedule measurements
are separate from PPO, which also includes optimizer cost and witness copies outside
its timed learn calls. No extrapolation to larger fleets or remote storage.

If the baseline exposes a material bottleneck, make at most one bounded application
change and rerun the same three-pair workload. Do not begin speculative core tuning
or confidence-framework work. Record a bad result rather than silently sampling data.

Baseline measured 11.59–12.28 s with drain versus 0.0356–0.0361 s off, 688 rows,
11 append publications, 6,764 backend files. Child append/commit accounted for
11.56–12.22 s; synchronous state copies took approximately 0.003 s. The one next
experiment increases publication batches from 64 to 512 rows (two 1 MiB transport
slots instead of two 128 KiB slots), without dropping or changing any event.
This trades more buffered/unpublished rows and later acknowledgment for fewer
publications; it does not pretend to eliminate per-value objects. Run the same
three pairs plus actual PPO/readback with `training.slurm --batch-rows 512`.
No further tuning is authorized by this experiment if the gain is marginal.

```sh
export PROTOTYPE_PYTHON=/absolute/path/to/python
export PROTOTYPE_DIR=/absolute/path/to/mjlab-reference
sbatch --partition=YOUR_PARTITION --gres=gpu:YOUR_GPU_TYPE:1 \
  --output=/task/scratch/training.log "$PROTOTYPE_DIR/training.slurm"
```

The coordinator bounds each phase to five minutes and removes its generated
backends, rollout witnesses and caches on exit. Task staging and private imports
are removed after preserving concise results. No raw models/traces are archived.
