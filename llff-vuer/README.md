# LLFF Camera Pose Viewer (Vuer)

Web-based 3D visualization of LLFF camera poses using [Vuer](https://github.com/vuer-ai/vuer).

Unlike the Rerun example (desktop app), this runs as a web server you can open in any browser.

## Quick Start

```bash
pip install vuer params-proto numpy

# Single scene
python visualize_llff.py --data-dir ~/datasets/fork

# Multiple scenes
python visualize_llff.py --data-dir /tmp/llff_scenes

# Open http://localhost:8012
```

## What It Shows

- **Cyan point cloud** — camera origins
- **Orange/white wireframes** — camera frustums (orange edges from origin, white for the image plane)
- Multiple scenes are displayed simultaneously
