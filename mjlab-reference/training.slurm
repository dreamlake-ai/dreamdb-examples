#!/bin/bash
#SBATCH --job-name=ddb-mjlab-training
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00
set -euo pipefail
: "${PROTOTYPE_PYTHON:?set an isolated or existing compatible Python}"
: "${PROTOTYPE_DIR:?set the prototype source directory}"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MUJOCO_GL=egl
cd "$PROTOTYPE_DIR"
"$PROTOTYPE_PYTHON" -B -u check_writer.py
"$PROTOTYPE_PYTHON" -B -u check_training.py "$@"
