"""Small RSL-RL adapter. Domain semantics stay outside DreamDB.

Only the fixed Cartpole actor group, no action clipping or observation
normalization. Records raw actor inputs and actions passed to env.step.
"""

from __future__ import annotations

import importlib.metadata
import platform
import tempfile
from pathlib import Path

import mujoco
from mjlab.rl import RslRlVecEnvWrapper
from writer import BoundedWriter


def attach_writer(env, root, *, batch_rows=512):
    with tempfile.TemporaryDirectory(prefix="ddb-training-model-") as directory:
        path = Path(directory) / "model.mjb"
        mujoco.mj_saveModel(env.sim.mj_model, str(path))
        model = path.read_bytes()
    dims = {
        "qpos": env.sim.mj_model.nq,
        "qvel": env.sim.mj_model.nv,
        "obs_t": 5,
        "obs_after": 5,
        "action": 1,
    }
    if env.sim.mj_model.nmocap:
        dims.update(mocap_pos=3 * env.sim.mj_model.nmocap, mocap_quat=4 * env.sim.mj_model.nmocap)
    metadata = {
        "run_id": root.name,
        "task": "Mjlab-Cartpole-Balance",
        "variation": "even-env termination at 3 steps; timeout at 4; noise disabled",
        "dimensions": dims,
        "mujoco_version": mujoco.__version__,
        "model_platform": {"system": platform.system(), "machine": platform.machine()},
        "mjlab_version": importlib.metadata.version("mjlab"),
        "rsl_rl_version": importlib.metadata.version("rsl-rl-lib"),
        "envs": env.num_envs,
        "seed": env.cfg.seed,
        "control_dt": env.step_dt,
        "decimation": env.cfg.decimation,
        "mocap_count": env.sim.mj_model.nmocap,
        "policy_input": "actor group before model normalization (disabled in this run)",
        "action": "unclipped policy output passed to environment action manager",
    }
    writer = BoundedWriter(
        root,
        metadata,
        model,
        slots=2,
        slot_bytes=max(131072, batch_rows * 2048),
        max_rows=batch_rows,
    )
    recorder = env.recorder_manager.get_term("dreamdb")
    recorder.attach(writer, batch_rows=batch_rows)
    return writer, recorder


class RecordingVecEnv(RslRlVecEnvWrapper):
    def __init__(self, env):
        # Writer must already be attached: base wrapper resets the environment.
        self.actor_observation = None
        super().__init__(env, clip_actions=None)

    def get_observations(self):
        obs = super().get_observations()
        self.actor_observation = obs["actor"]
        return obs

    def step(self, actions):
        if self.actor_observation is None:
            raise RuntimeError("get_observations must precede the first step")
        recorder = self.unwrapped.recorder_manager.get_term("dreamdb")
        recorder.begin_step(self.actor_observation, actions)
        result = super().step(actions)
        self.actor_observation = result[0]["actor"]
        return result
