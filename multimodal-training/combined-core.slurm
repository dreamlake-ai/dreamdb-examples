#!/bin/bash
#SBATCH --job-name=ddb-combined-train
#SBATCH --partition=gpu_a100
#SBATCH --gres=gpu:rtxpro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:15:00
set -euo pipefail
task_root="$PWD"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MUJOCO_GL=egl
export TMPDIR="$task_root/tmp"
mkdir -p "$TMPDIR" "$task_root/capture"
export XDG_CACHE_HOME="$TMPDIR/cache" CUDA_CACHE_PATH="$TMPDIR/cuda"
runtime=/home/tom/verbmotion/.venv/bin/python
cd source
export PYTHONPATH="$task_root/sdk-baseline"
timeout 240 "$runtime" -B -u amplification.py capture "$task_root/capture"
for variant in baseline combined combined baseline; do
    export PYTHONPATH="$task_root/sdk-$variant"
    echo "VARIANT $variant"
    "$runtime" -B -c 'import dreamdb._native as native; print("NATIVE", native.__file__)'
    timeout 180 "$runtime" -B -u ondemand.py exact "$task_root/capture"
done
