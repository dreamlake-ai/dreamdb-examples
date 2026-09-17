# On-demand producer result

Issue #12. Slurm 147490, bos14-node-085, 2026-09-16, COMPLETED exit 0,
62 seconds including capture and four independent training processes. Requested
4 CPUs / 16 GiB / one RTX PRO 6000; allocation reported 32 CPUs. Python 3.12.3,
DreamDB 0.0.13, mjlab 1.6.0, MuJoCo 3.11.0, Torch 2.9.1, NumPy 2.5.3,
Pillow 12.3.0. Source snapshot (ephemeral task dataset):
`d3kola7wfrh46nn6u7mvk4pusatgtppdfpl4xizn3edaxjvjyg3nu`.

No ready artifact. Every batch selects native PNG/sensor/action records, decodes
and transforms according to this application's current four-frame task. Same
156 training windows, two epochs, 20 real optimizer updates per mode. Captured
identity-derived expected order, pixels after float conversion, sensors and target
actions all compared exactly at every delivered batch. Four runs passed.

| Actual run order | Loop s | Consumer wait s | Producer read/convert s | Completed compute s | First batch s |
|---|---:|---:|---:|---:|---:|
| serial | 5.499 | 5.232 | 4.984 | .203 | .804 |
| prefetch | 5.302 | 4.997 | 4.916 | .200 | .677 |
| prefetch | 5.055 | 4.803 | 4.731 | .200 | .613 |
| serial | 5.197 | 4.935 | 4.714 | .198 | .500 |

Each run: 156 projected SDK range calls, 1,098 selected PNG decodes. Counters are
SDK calls, not disk IO. Completed transfer totaled 5.35–6.37 ms. Witness checks
took 30–45 ms and are included in loop elapsed; producer may overlap these too,
so this is not a pure estimate of GPU-overlap savings. Torch/model initialization
and witness loading precede loop timing; Reader initialization and worker spawn
are included. Warm filesystem effects were not reset.

Paired loop reductions were 3.6% and 2.7%; this small sample is not evidence of a
general speedup. Roughly 95% of the prefetch loop still waits for input. The real
model's ~0.2 s compute cannot hide ~4.7–4.9 s of producer work. More queued batches
cannot resolve that average-rate deficit. No artificial compute was added.

## Memory boundary and cost

Maximum delivered batch payload was 3,147,328 bytes. Queue capacity two, with one
producer and one consumer batch, bounds logical batch residency to four batches
(12,589,312 payload bytes at this maximum), **not total allocation**: IPC copies,
serialization, raw/converted temporaries, Reader state, SDK buffers, pinned/runtime
allocations and witnesses are outside that count. Parent peak RSS was
1,439,996–1,461,352 KiB; producer peaks 750,792 / 750,824 KiB. Separate process RSS
peaks are not a simultaneous physical-memory sum (shared pages may overlap).
This run does not establish large-dataset total-memory bounds.

## Interpretation and next boundary

On-demand application-defined conversion is viable and preserves actual training
inputs, but prefetch alone did not make this workload compute-bound. There are
192 distinct training frames, decoded 1,098 times across overlapping shuffled
windows and epochs. That is a concrete opportunity for a bounded raw-record or
decoded-frame cache keyed by pinned snapshot/anchor, without persisting a fixed
training format. It remains unimplemented; these aggregate timings do not prove
whether SDK reads or PNG decode dominates, nor predict cache performance.

Before selecting the next optimization, separate public read time from selected
decode/assembly time. A cache should target measured repeated work and retain a
byte budget; do not simply increase worker count or expand the entire dataset.
Task-specific augmentation must remain downstream, not accidentally frozen in a
decoded cache. Remote download, arbitrary modalities, video GOP decode, cold
storage and throughput at scale are outside this experiment.

## Reproduce and cleanup

See ONDEMAND.md and ondemand.slurm. In an isolated Slurm task directory install
DreamDB 0.0.13 with `python3 -m pip install --no-deps --target sdk dreamdb==0.0.13`,
copy this directory to `source/`, then submit `source/ondemand.slurm`. The script
uses the existing compatible mjlab runtime and keeps the capture for diagnosis.
After capturing the concise results remove the task directory. No raw dataset or
run log is archived here. No core changes, formal CI run, or core testbox verdict.
