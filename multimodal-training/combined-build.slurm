#!/bin/bash
#SBATCH --job-name=ddb-combined-build
#SBATCH --partition=gpu_a100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:30:00
set -euo pipefail
task_root="$PWD"
export PATH="/home/tom/.cargo/bin:$PATH"
export CARGO_BUILD_JOBS=4 CARGO_TARGET_DIR="$task_root/target"
export PYTHONDONTWRITEBYTECODE=1
runtime=/home/tom/verbmotion/.venv/bin/python
rustc --version
cargo --version
for variant in baseline combined; do
    echo "BUILD_START $variant $(date -u +%FT%TZ)"
    git -C "$task_root/core-$variant" rev-parse HEAD
    "$task_root/tools/bin/maturin" build --release --locked \
        --compatibility linux --interpreter "$runtime" \
        --manifest-path "$task_root/core-$variant/dreamdb-dataset-python/Cargo.toml" \
        --out "$task_root/wheel-$variant"
    wheels=("$task_root/wheel-$variant/"*.whl)
    test "${#wheels[@]}" -eq 1
    sha256sum "${wheels[0]}"
    python3 -m pip install --disable-pip-version-check --no-deps \
        --target "$task_root/sdk-$variant" "${wheels[0]}"
    echo "BUILD_END $variant $(date -u +%FT%TZ)"
done
