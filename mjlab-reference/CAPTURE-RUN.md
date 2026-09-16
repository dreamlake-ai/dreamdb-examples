# Bounded capture acceptance run

Run plan written before submission; completed results are in FINDINGS.md.

- One Slurm GPU node, one task, four requested CPUs, 16 GiB requested memory,
  ten-minute job limit. Actual allocation may be whole-node on select/linear.
- Existing mjlab 1.6.0 / PyTorch 2.9.1+cu128 / MuJoCo(-Warp) 3.11.0 / Warp 1.14.0
  / NumPy 2.5.3 environment; DreamDB 0.0.13 installed into a task-private import
  directory, not into the user's existing environment.
- Cartpole Balance, 32 worlds, 11 control steps, seed 71, observation corruption
  disabled. Explicit acceptance variation: even environments terminate at step 3;
  every environment times out at step 4. This is not the native task's termination
  rule and not a training run.
- Actual scene has one mocap body. Include all mocap position/quaternion state;
  reject nonzero actuator activation state or expanded model fields in this version.
- Automatic-reset capture, then separate manual-reset reference execution using
  the same inputs, then a separate public-SDK reader. Compare identity/flags
  exactly, numeric states with rtol=1e-5/atol=1e-6 across independent GPU runs.
  Storage-only acceptance separately checks exact array bytes.
- One 128 KiB shared CPU slot, batches of at most 64 event rows. Explicit
  synchronous GPU-to-host snapshots; slot reused only after publication ack.
- No S3/production data, policy training, cluster configuration changes or worker SSH.
- Generated database, reference trace and compilation caches go under the
  coordinator's temporary directory and are removed on normal completion/failure.
  Scheduler timeout/kill cleanup must be checked explicitly if one occurs.

Portable submission (replace site-specific values):

```sh
export PROTOTYPE_PYTHON=/absolute/path/to/python
export PROTOTYPE_DIR=/absolute/path/to/mjlab-reference
sbatch --partition=YOUR_PARTITION --gres=gpu:YOUR_GPU_TYPE:1 \
  --output=/task/scratch/capture.log "$PROTOTYPE_DIR/capture.slurm"
```

The script executes the Python program directly inside the allocation; no nested
srun step. The local smoke first exercises a one-slot writer and kills only its
own spawned child to establish failure propagation/no clean completion marker.
Then the GPU check exercises actual pre/post-reset recording. No test-of-test
framework is introduced. Save a concise outcome, not a raw evidence archive.
