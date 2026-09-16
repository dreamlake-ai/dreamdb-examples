"""One independent restore/render check of the real captured Cartpole trace."""

from __future__ import annotations

import hashlib
import json

import mujoco
import numpy as np
from playback import Playback


def check(root):
    receipt = json.loads((root / "receipt.json").read_text())
    witnesses = json.loads((root / "poses.json").read_text())
    player = Playback((root / "backend").as_uri(), receipt["manifest"])
    images = set()
    max_pose_error = 0.0
    with mujoco.Renderer(player.model, height=240, width=320) as renderer:
        for witness in witnesses:
            player.select(witness["env_id"], witness["episode_id"])
            row = player.seek(witness["step"])
            for name in ("qpos", "qvel", "mocap_pos", "mocap_quat"):
                np.testing.assert_array_equal(
                    getattr(player.data, name).reshape(-1), row[name].reshape(-1)
                )
            for name in ("xpos", "xmat"):
                got = getattr(player.data, name).reshape(-1)
                want = np.asarray(witness[name]).reshape(-1)
                np.testing.assert_allclose(got, want, rtol=1e-5, atol=1e-6, err_msg=str(witness))
                max_pose_error = max(max_pose_error, float(np.max(np.abs(got - want))))
            rgb = player.render(renderer)
            assert rgb.shape == (240, 320, 3) and rgb.dtype == np.uint8
            assert rgb.max() > rgb.min(), "render returned a uniform frame"
            images.add(hashlib.sha256(rgb.tobytes()).hexdigest())
    assert len(images) > 1, "different recorded poses did not produce different frames"

    # The desktop controls call these same methods. Native window/key delivery
    # is not exercised by this headless job.
    player.select(0, 0)
    player.tick(1)
    assert player.index == 0 and player.paused
    player.toggle_pause()
    dt = player.rows[1]["sim_time"] - player.rows[0]["sim_time"]
    player.tick(dt)
    assert player.index == 1
    player.step(-1)
    assert player.index == 0 and player.paused
    player.seek(2)
    assert player.rows[player.index]["terminated"]
    player.seek(-1)
    player.toggle_pause()
    player.tick(10)
    assert player.index == len(player.rows) - 1 and player.paused
    try:
        player.select(0, 3)
    except ValueError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("incomplete tail accepted without explicit opt-in")
    player.select(0, 3, allow_incomplete=True)
    assert player.status == "incomplete"
    print(
        "PLAYBACK_ACCEPTANCE "
        + json.dumps(
            {
                "result": "PASS",
                "pose_samples": len(witnesses),
                "distinct_rendered_frames": len(images),
                "max_pose_error": max_pose_error,
                "controls": "pause/step/seek/timed advance",
                "incomplete": "explicit opt-in",
                "desktop_window": "not tested",
            }
        ),
        flush=True,
    )
