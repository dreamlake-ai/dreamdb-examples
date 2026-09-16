"""State playback from a pinned DreamDB snapshot; no mjlab or Torch import.

Restores recorded state and calls mj_forward, never mj_step. The saved MJB and
projected fields are the only model/state inputs. One selected episode is held
in memory; this is a small reference viewer, not a streaming video service.
"""

from __future__ import annotations

import argparse
import platform
import queue
import tempfile
import time
from pathlib import Path

import dreamdb
import mujoco
import numpy as np
from store import FLAGS, IDENTITY, MOCAP_FIELDS, STATE, episode_status, read_episode, read_header


class Playback:
    def __init__(self, backend: str, manifest: str):
        self.dataset = dreamdb.Dataset.open_by_manifest(manifest, backend=backend)
        self.metadata, model_bytes = read_header(self.dataset)
        if self.metadata["mujoco_version"] != mujoco.__version__:
            raise ValueError("saved MJB requires the recorded MuJoCo version")
        expected_platform = self.metadata.get("model_platform")
        actual_platform = {"system": platform.system(), "machine": platform.machine()}
        if expected_platform is None or expected_platform != actual_platform:
            raise ValueError(
                "saved MJB platform absent or different; cross-platform loading unverified"
            )
        with tempfile.TemporaryDirectory(prefix="ddb-playback-model-") as temp:
            model_path = Path(temp) / "model.mjb"
            model_path.write_bytes(model_bytes)
            self.model = mujoco.MjModel.from_binary_path(str(model_path))
        dims = self.metadata["dimensions"]
        if (self.model.nq, self.model.nv) != (dims["qpos"], dims["qvel"]):
            raise ValueError("model and stored state dimensions disagree")
        if self.model.na:
            raise ValueError("actuator activation state is not supported by this prototype")
        if self.model.nmocap and (
            dims.get("mocap_pos") != 3 * self.model.nmocap
            or dims.get("mocap_quat") != 4 * self.model.nmocap
        ):
            raise ValueError("model requires mocap state not supplied by this recording")
        self.data = mujoco.MjData(self.model)
        self.rows = []
        self.index = 0
        self.paused = True
        self._elapsed = 0.0
        self.status = "unselected"

    def select(self, env_id: int, episode_id: int, *, allow_incomplete=False):
        fields = (
            IDENTITY
            + FLAGS
            + STATE
            + [name for name in MOCAP_FIELDS if name in self.metadata["dimensions"]]
        )
        rows = read_episode(self.dataset, env_id, episode_id, fields=fields)
        if not rows:
            raise ValueError("episode not found")
        status = episode_status(rows)
        if status != "complete" and not allow_incomplete:
            raise ValueError("episode is incomplete; explicitly allow its available prefix")
        if rows[0]["kind"] != "reset":
            raise ValueError("cannot play an episode without its initial state")
        if any(b["sim_time"] <= a["sim_time"] for a, b in zip(rows, rows[1:], strict=False)):
            raise ValueError("episode simulation times must strictly increase")
        self.rows, self.status = rows, status
        self.index = 0
        self.paused = True
        self._elapsed = 0.0
        return self.restore()

    def restore(self):
        if not self.rows:
            raise ValueError("select an episode first")
        row = self.rows[self.index]
        # Remove any previous-frame solver/control history. Nothing is integrated.
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:] = row["qpos"]
        self.data.qvel[:] = row["qvel"]
        self.data.time = row["sim_time"]
        if self.model.nmocap:
            self.data.mocap_pos[:] = row["mocap_pos"].reshape(self.model.nmocap, 3)
            self.data.mocap_quat[:] = row["mocap_quat"].reshape(self.model.nmocap, 4)
        mujoco.mj_forward(self.model, self.data)
        return row

    def seek(self, step: int):
        """-1 selects the reset state; nonnegative values select transition step_id."""
        for i, row in enumerate(self.rows):
            if (step == -1 and row["kind"] == "reset") or (
                row["kind"] == "transition" and row["step_id"] == step
            ):
                self.index = i
                self.paused = True
                self._elapsed = 0.0
                return self.restore()
        raise ValueError(f"step {step} is not present")

    def step(self, delta=1):
        if not self.rows:
            raise ValueError("select an episode first")
        self.index = min(max(self.index + delta, 0), len(self.rows) - 1)
        self.paused = True
        self._elapsed = 0.0
        return self.restore()

    def toggle_pause(self):
        self.paused = not self.paused

    def tick(self, elapsed: float):
        """Advance using recorded simulation-time deltas, not logical anchor gaps."""
        if not np.isfinite(elapsed) or elapsed < 0:
            raise ValueError("elapsed time must be finite and nonnegative")
        if self.paused or not self.rows:
            return
        self._elapsed += elapsed
        while self.index + 1 < len(self.rows):
            delay = self.rows[self.index + 1]["sim_time"] - self.rows[self.index]["sim_time"]
            if self._elapsed < delay:
                break
            self._elapsed -= delay
            self.index += 1
            self.restore()
        if self.index == len(self.rows) - 1:
            self.paused = True

    def camera(self):
        # Prefer the asset's authored camera over guessing a useful scene extent.
        for i in range(self.model.ncam):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_CAMERA, i)
            if name == "fixed" or (name and name.endswith("/fixed")):
                return i
        camera = mujoco.MjvCamera()
        mujoco.mjv_defaultCamera(camera)
        camera.lookat[:] = self.model.stat.center
        camera.distance = max(1.0, self.model.stat.extent * 2)
        camera.azimuth, camera.elevation = 90, -20
        return camera

    def render(self, renderer):
        renderer.update_scene(self.data, camera=self.camera())
        return renderer.render()


def view(player):
    """Desktop convenience UI; controls use the same tested Playback methods."""
    import mujoco.viewer

    keys = queue.SimpleQueue()
    print("Space play/pause; Left/Right step; Home reset; End last; 0-9 seek fraction")
    with mujoco.viewer.launch_passive(player.model, player.data, key_callback=keys.put) as viewer:
        camera = player.camera()
        with viewer.lock():
            if isinstance(camera, int):
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = camera
            else:
                viewer.cam.lookat[:] = camera.lookat
                viewer.cam.distance = camera.distance
                viewer.cam.azimuth, viewer.cam.elevation = camera.azimuth, camera.elevation
        last = time.monotonic()
        while viewer.is_running():
            now = time.monotonic()
            with viewer.lock():
                while not keys.empty():
                    key = keys.get()
                    if key == 32:
                        player.toggle_pause()
                    elif key in (262, 263):
                        player.step(1 if key == 262 else -1)
                    elif key == 268:
                        player.seek(-1)
                    elif key == 269:
                        player.step(len(player.rows))
                    elif 48 <= key <= 57:
                        index = round((len(player.rows) - 1) * (key - 48) / 9)
                        player.step(index - player.index)
                player.tick(now - last)
            viewer.sync()
            last = now
            time.sleep(0.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["render", "view"])
    parser.add_argument("--backend", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--env", type=int, required=True)
    parser.add_argument("--episode", type=int, required=True)
    parser.add_argument("--step", type=int, default=-1, help="-1 is initial state")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument(
        "--output", type=Path, help="render: new PPM image path (never overwritten)"
    )
    args = parser.parse_args()
    if args.mode == "render" and args.output is None:
        parser.error("render requires --output")
    player = Playback(args.backend, args.manifest)
    player.select(args.env, args.episode, allow_incomplete=args.allow_incomplete)
    player.seek(args.step)
    if args.mode == "view":
        view(player)
    else:
        with mujoco.Renderer(player.model, height=240, width=320) as renderer:
            rgb = player.render(renderer)
        with args.output.open("xb") as output:
            output.write(b"P6\n320 240\n255\n" + rgb.tobytes())
        print(f"Rendered {player.status} episode at {args.output}")


if __name__ == "__main__":
    main()
