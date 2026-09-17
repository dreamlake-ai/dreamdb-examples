#!/bin/bash
#SBATCH --job-name=ddb-amp-repeat
#SBATCH --partition=gpu_a100
#SBATCH --gres=gpu:rtxpro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=4G
#SBATCH --time=00:02:00
set -euo pipefail
task_root="$PWD"
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4
export PYTHONPATH="$task_root/sdk" TMPDIR="$task_root/tmp"
cd source
timeout 60 strace -f -ttt -qq -s 80 -yy -e trace=openat,read,pread64,write \
    -o "$task_root/trace-narrow-repeat.log" /home/tom/verbmotion/.venv/bin/python -B -u \
    amplification.py narrow-repeat "$task_root/capture"
