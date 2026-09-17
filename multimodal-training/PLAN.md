# Design and bounded execution plan

Written before implementation for examples #6. Parent examples main `a744371`;
core source inspection at `c6b31ab`; initial runtime is released DreamDB 0.0.13.

1. `data.py`: public schema/writer, receipt, pinned projected page reader, episode
   catalogue, batch page union and per-batch PNG decode reuse. Separate from Torch
   and mjlab; no private object parser or modification to earlier prototypes.
2. `run.py capture`: actual fixed Cartpole simulation under Slurm; copy pre-state,
   render and encode, apply the documented action, add outcome flags, batch append.
   Temporary raw pixel/state/action witnesses are independent of database decode.
3. `run.py train`: a new process opens the receipt snapshot, compares requested
   windows against capture witnesses, compares naive and coalesced reads, then
   runs real CNN+sensor optimization using database output only.
4. `run.py preflight`: tiny synthetic image fixture through the real released SDK
   checks mixed image/array/scalar write+projected read locally before GPU spend.
   This is not the real-scene verdict and does not replace it.
5. One Slurm GPU, 4 requested CPU, 16 GiB, 10-minute limit. Existing runtime is
   read-only; SDK/Pillow dependencies in private imports as needed. Capture and
   training have separate processes, 240 s phase limits, and task-private data/
   caches. No controller training, worker SSH or cluster configuration changes.

## Evidence boundary

Primary claim: actual RGB+sensor+annotation recordings become exact four-frame
training samples and support optimization. Reachable failures: wrong frame/clock,
cross-reset window, changed sensor/action, train/validation leakage, missing
multimodal payload or full-result materialization. Minimum direct evidence:
public SDK reopen, all small-recording sample identities/pixels/array bytes
checked against capture witnesses, split identity disjointness, then finite loss
and changed finite parameters from real gradient steps. No validation of validators.

Compare identical requests/fields with one-window-at-a-time reads. Alternate the
two read modes by batch order, without cold-cache assertions or timing thresholds.
Measure catalogue and first-batch latency, elapsed read/decode, actual SDK call
count, returned projected bytes, unique decoded frames, output bytes, process
RSS high-water and training loader-blocked versus compute wall time. Returned
payload bytes are not filesystem bytes, object GETs or network bandwidth. No IO
proxy will be labeled physical IO. No unbounded tuning if results are poor.

No new API/core issue unless this application demonstrates a generic blocker.
If core work is needed, stop that path for issue/spec/design and testbox first.
After the direct run, record conclusions and reproduction, submit one formal PR,
and clean generated datasets/models/witnesses/caches, task envs and worktrees after
durable preservation. Keep no raw evidence archive or credentials.
