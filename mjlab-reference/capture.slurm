#!/bin/bash
# Select partition/GRES at submission; names and resource configuration are site-specific.
#SBATCH --job-name=ddb-mjlab-reference
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00
set -euo pipefail
: "${PROTOTYPE_PYTHON:?absolute Python path with the pinned dependencies}"
: "${PROTOTYPE_DIR:?absolute path to mjlab-reference}"
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=4
export MUJOCO_GL=egl
cd "$PROTOTYPE_DIR"
"$PROTOTYPE_PYTHON" -B -u check_writer.py
"$PROTOTYPE_PYTHON" -B -u check_capture.py
