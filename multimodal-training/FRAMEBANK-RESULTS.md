# Lossless frame-bank result — 2026-09-16

PASS, one bounded paired Slurm run. Same actual capture, snapshot, sample split,
float32 values, shared model and seeded shuffle in both layouts. Eight worlds,
two 16-step episodes each: 256 source frames, 208 four-frame windows / 832 frame
slots. Both paths use 156 training / 52 validation samples and 20 optimizer steps.

## Storage and local-load result

| Metric | Full-window v1 | Unique-frame bank |
| --- | ---: | ---: |
| Tensor files, excluding manifest | 52 | 5 |
| Artifact bytes, including manifest | 40,934,870 | 12,601,579 |
| Locally copied tensor bytes | 40,921,920 | 12,597,184 |
| Local copy + hash | 0.492 s | 0.133 s |
| Host gather, all 20 batches | 2.658 ms | 2.668 ms |
| Submission through completed H2D, wall time | 3.070 ms | 3.081 ms |
| Sum: data ready for compute | **5.729 ms** | **5.749 ms** |
| H2D CUDA event duration, inside preceding wall time | 2.748 ms | 2.752 ms |
| First batch gather + completed H2D | 0.511 ms | 0.532 ms |
| File mapping / shape-check initialization | 91.46 ms | 4.87 ms |
| Torch/CUDA/model/buffer setup, including mapping | 1.726 s | 1.550 s |
| Optimizer compute | 0.206 s | 0.195 s |
| Process peak RSS, KiB | 1,562,580 | 1,512,436 |

Artifact size fell **69.2%**, without meaningful observed local-load regression
in this run. No precision reduction or discarded sample: all 208 output windows
were compared by dtype/shape/bytes to v1, and both trainers checked all inputs
against capture witnesses. One completed GPU batch copy per layout matched exactly.
Finite changed parameters and validation passed. Validation MSE was
0.000156335599 / 0.000156335651; floating training trajectories are not promised
bit-identical despite identical inputs. This is not a policy-quality claim.

Original database files, including metadata/history, total 856,034 B. The bank
is still **14.7x** that size because normalized float32 expands PNG; this is not
a pure codec ratio. H2D volume stays 61,362,912 B across the two epochs: models
still receive the same inputs. Fewer artifact bytes is not measured WAN performance.

These are single-run warm-file figures, not statistical equivalence or theoretical
limits. Fixed v1→bank execution order; acceptance checks warm file pages. RSS
includes framework/CUDA/witnesses, not isolated loader memory. Initialization and
first batch are reported, not hidden. Existing three warm contiguous-copy
references were about 0.174–0.207 ms for v1 and 0.174–0.199 ms for the bank.
No new control framework or unbounded tuning. A contiguous frame-slice reshape
is a view; it does not perform pixel conversion in the loop.

## Upstream cost is not erased

Original materialization ran once: 3.636 s (selection 0.240, read/decode 2.722,
transform 0.00778, write/hash 0.664). Repacking added **0.282 s**, excluding the
subsequent all-window comparison. This first implementation needs the old ready
artifact and its transient space; it does not yet build directly from the database.
Both delivered copies exist only for this comparison and are cleaned afterwards.
No end-to-end claim omits these upstream steps.

## Reproduction and cleanup

CPU: `python -B pipeline.py preflight-frames`. Real public-SDK writes cover two
episodes, one with six steps yielding overlapping windows; reordered and repeated
requests also match after repack/verified byte delivery. Ruff check/format and
git diff --check passed.

GPU: `python -B -u pipeline.py compare-frames` under the bounded Slurm setup in
README. Capture/build/trainers are separate processes; the original database path
is unavailable during both training runs. Temporary source snapshot:
`dy6oe6sjwrl2byjmqbzwvxm43vm2zishehb5qfvhmezvm237by3e6`. New runs create and
check their own snapshots; this one was cleaned, not published for reuse.

Runtime: Linux x86_64 / RTX PRO 6000, Python 3.12.3, private DreamDB 0.0.13,
mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1+cu128, NumPy 2.5.3, Pillow 12.3.0.
One GPU, four CPUs/16 GiB requested; whole 32-CPU node allocated, Torch/OMP
limited to four threads. Job completed in 44 s, exit 0. No core change, shared
runtime mutation, production writes, MinIO, release or extra CI.

Coordinator cleaned datasets/artifacts/witnesses/cache. Task staging/imports/logs
and local worktree are removed after preserving source and these concise results;
no raw evidence archive is retained.
