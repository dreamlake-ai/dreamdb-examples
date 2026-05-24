# rerun-demo

Visualize LLFF camera poses from DreamDB datasets using [Rerun](https://rerun.io).

![rerun](https://img.shields.io/badge/rerun-0.22+-blue)
![python](https://img.shields.io/badge/python-3.9+-green)

## Installation

```bash
pip install rerun-sdk dreamdb-dataset numpy Pillow
```

## Usage

### From a local LLFF directory

Point `--data-dir` at a directory containing `poses_bounds.npy` (and optionally
an `images/` subdirectory):

```bash
python visualize_llff.py --data-dir ./data/fern
```

### From a DreamDB dataset

Provide the `--backend` URL of a DreamDB server:

```bash
python visualize_llff.py --backend http://localhost:8012/my-dataset
```

You can optionally specify `--scene` to select a particular key within the
dataset.

### Options

| Flag | Description |
|------|-------------|
| `--data-dir PATH` | Path to a local LLFF scene directory |
| `--backend URL` | DreamDB backend URL |
| `--scene NAME` | Scene or key name within the DreamDB dataset |
| `--no-images` | Skip loading source images |
| `--connect` | Connect to an already-running Rerun viewer |

## LLFF Pose Format

The `poses_bounds.npy` file contains an `(N, 17)` array where each row is:

- **Columns 0--14**: A `3x5` matrix `[R | t | hwf]` stored in column-major
  order. The `3x4` portion `[R | t]` is the camera-to-world transformation
  matrix, and the last column holds `[height, width, focal_length]`.
- **Columns 15--16**: Near and far depth bounds.

## License

MIT
