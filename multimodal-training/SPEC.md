# Multimodal training reference v1

Issue: [examples #6](https://github.com/dreamlake-ai/dreamdb-examples/issues/6).
External application contract, not a DreamDB protocol or new training product.

## Data and clock

One fixed-model Cartpole run, eight parallel worlds, two 16-control-step episodes
per world. Use native timeout, observation noise disabled, seed 71. Capture
images by restoring copied pre-action qpos/qvel/mocap/time into the original
MuJoCo model and calling forward/render, never integrating the renderer state.
64x64 RGB, lossless PNG stored as a real DreamDB image field. Sensor is the
concatenated pre-action qpos/qvel as little-endian float32; action is the exact
float32 scalar passed to env.step. A bounded state-feedback demonstration policy
is defined by the capture code; it is neither a trained expert nor a quality claim.

Database anchor is a unique dense record ordinal, NOT physical nanoseconds.
Each row has env_id, episode_id, step_id, sim_time, image, sensor, action,
terminated, truncated. Image and sensor refer to the same pre-action state;
terminal flags describe that action's outcome. No post-reset image is substituted.
Explicit metadata at anchor zero records encoding, dimensions, policy, versions,
clock meaning and camera. Publish a receipt with the exact Manifest and exclusive
end_anchor. Original dataset is never overwritten and no live Ref is followed.

## Samples and split

A sample contains four consecutive images and sensors from one complete episode;
its label is the last row's action. Windows overlap, do not cross resets and do
not include future state. Require every row/image; no padding, missing-value
imputation or fabricated termination. Float timestamps are recorded values, not
an alignment heuristic. Asynchronous sensor alignment is out of scope.

Split complete episodes before window construction: env_id 0–5 for training,
6–7 for validation. No episode or frame appears in both splits. This measures
held-out simulation trajectories, not task/domain generalization. Shuffle training
sample order with a fixed seed; physical reads can be reordered within a batch
but must return exactly that requested order. No change in shuffle semantics.

## Read contract and bounds

Open by Manifest. Scan only identity/time/terminal columns over an explicit
finite prefix, validating contiguous ordinals and episode steps. Keep this small
catalogue in memory (O(record count), capped at 4096 rows). Read only image/sensor/
action for selected samples through projected ordinal pages (default 32 rows).
Union pages across the batch and decode each selected image once per call.
Return NumPy batches: RGB uint8 [B,4,64,64,3], sensor float32 [B,4,D], target
float32 [B,1], and exact ordinal identities. Maximum 16 requests per batch.

The reader is synchronous with natural consumer backpressure. It does not claim
prefetch, worker sharding or a generic lazy multi-modality core stream. Existing
iter_all_batches materializes each selected page; fixed payload dimensions and
explicit page/request/scan caps bound application work, not native metadata,
connector caches, decoder temporaries or total RSS. No all-field hydration.

## Training and claims

One small CNN over four frames plus a sensor MLP, MSE imitation loss, two epochs
and validation. Decode/normalization/collation/Torch remain in the application.
Finite loss, finite changed parameters and actual optimizer updates establish
that stored data can train a model. They do not establish policy quality,
convergence, image necessity or improved control; a sensor-only policy may suffice.

Use a local file backend on one Slurm GPU. No S3, video codec/GOP, resizing,
augmentation, expert training, production data, multi-node workers or core patch.
Do not present this bounded reference as a ready large-corpus training service.
