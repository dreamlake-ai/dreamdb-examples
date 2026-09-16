"""mjlab 1.6.0 Cartpole-only recorder. Import only in the simulation process."""

from __future__ import annotations

import numpy as np
import torch
from mjlab.managers.recorder_manager import RecorderTerm


def host(tensor):
    # Deliberately synchronous baseline. Own values before reset/next step mutation.
    return tensor.detach().cpu().numpy().copy()


class DreamDBRecorder(RecorderTerm):
    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self.writer = None
        self.batch_rows = 64
        self.rows = []
        self.episodes = np.full(env.num_envs, -1, dtype=np.int64)
        self.steps = np.zeros(env.num_envs, dtype=np.int64)
        self.sim_step = 0
        self.before = None
        self.actions = None

    def attach(self, writer, batch_rows=64):
        self.writer = writer
        self.batch_rows = batch_rows

    def begin_step(self, observation, action):
        if self.writer is None or self.before is not None:
            raise RuntimeError("attach writer and complete previous step first")
        self.before = host(observation)
        self.actions = host(action)
        self.sim_step += 1

    def _emit(self, row):
        self.rows.append(row)
        if len(self.rows) >= self.batch_rows:
            self.flush()

    def flush(self):
        if self.rows:
            self.writer.submit(self.rows)
            self.rows = []

    def _state(self, ids):
        mocap = {}
        if self._env.sim.mj_model.nmocap:
            for name in ["mocap_pos", "mocap_quat"]:
                mocap[name] = host(getattr(self._env.sim.data, name)[ids]).reshape(len(ids), -1)
        return (
            host(self._env.sim.data.qpos[ids]),
            host(self._env.sim.data.qvel[ids]),
            host(self._env.sim.data.time[ids]).reshape(-1),
            mocap,
        )

    def record_post_reset(self, env_ids):
        if self.writer is None:
            raise RuntimeError("reset called before recorder writer attached")
        ids = host(env_ids).tolist()
        pos, vel, times, mocap = self._state(env_ids)
        obs = host(self._env.obs_buf["actor"][env_ids])
        for i, env in enumerate(ids):
            self.episodes[env] += 1
            self.steps[env] = 0
            self._emit(
                {
                    "kind": "reset",
                    "env_id": env,
                    "episode_id": int(self.episodes[env]),
                    "step_id": 0,
                    "sim_step": self.sim_step,
                    "sim_time": float(times[i]),
                    "qpos": pos[i],
                    "qvel": vel[i],
                    "obs_after": obs[i],
                    **{name: values[i] for name, values in mocap.items()},
                }
            )

    def _transitions(self, env_ids, terminal):
        if self.before is None:
            raise RuntimeError("call begin_step with the actual policy input/action")
        ids = host(env_ids).tolist()
        if not ids:
            return
        pos, vel, times, mocap = self._state(env_ids)
        rewards = host(self._env.reward_buf[env_ids])
        terminated = host(self._env.reset_terminated[env_ids])
        truncated = host(self._env.reset_time_outs[env_ids])
        after = None if terminal else host(self._env.obs_buf["actor"][env_ids])
        for i, env in enumerate(ids):
            row = {
                "kind": "transition",
                "env_id": env,
                "episode_id": int(self.episodes[env]),
                "step_id": int(self.steps[env]),
                "sim_step": self.sim_step,
                "sim_time": float(times[i]),
                "qpos": pos[i],
                "qvel": vel[i],
                "obs_t": self.before[env],
                "action": self.actions[env],
                "reward": float(rewards[i]),
                "terminated": bool(terminated[i]),
                "truncated": bool(truncated[i]),
                "next_observation_valid": not terminal,
                **{name: values[i] for name, values in mocap.items()},
            }
            if after is not None:
                row["obs_after"] = after[i]
            self._emit(row)
            self.steps[env] += 1

    def record_pre_reset(self, env_ids):
        self._transitions(env_ids, terminal=True)

    def record_post_step(self):
        ids = torch.nonzero(~self._env.reset_buf, as_tuple=False).flatten()
        self._transitions(ids, terminal=False)
        self.before = self.actions = None

    def close(self):
        # Explicit owner finish is required; env.close after an error must not
        # accidentally publish run_end or flush an unaccepted partial step.
        if self.writer is not None:
            self.writer.abort()
