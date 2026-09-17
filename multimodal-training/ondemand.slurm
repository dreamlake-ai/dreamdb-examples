#!/bin/bash
#SBATCH --job-name=ddb-ondemand
#SBATCH --partition=gpu_a100
#SBATCH --gres=gpu:rtxpro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00
set -euo pipefail
# Submit from isolated task directory containing source/ and sdk/.
task_root="$PWD"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MUJOCO_GL=egl
export PYTHONPATH="$task_root/sdk"
export TMPDIR="$task_root/tmp"
mkdir -p "$TMPDIR" "$task_root/capture"
export XDG_CACHE_HOME="$TMPDIR/cache" CUDA_CACHE_PATH="$TMPDIR/cuda"
cd source
runtime=/home/tom/verbmotion/.venv/bin/python
timeout 240 "$runtime" -B -u run.py capture "$task_root/capture"
for mode in serial prefetch prefetch serial; do
    timeout 120 "$runtime" -B -u ondemand.py "$mode" "$task_root/capture"
done
