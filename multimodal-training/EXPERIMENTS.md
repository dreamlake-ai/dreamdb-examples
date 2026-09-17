# Experiment map

For the application entry point, use [README.md](README.md). These are optional
alternatives and historical measurements, not steps every user must execute.
Each result is scoped to its recorded source/package and workload. Test data
and private wheels were cleaned; reproduction creates fresh task artifacts.

## On-demand raw data: no fixed training format at ingestion

| Question | Contract / implementation | Measured result |
|---|---|---|
| Does basic image/sensor storage feed a real model correctly? | [SPEC](SPEC.md), `run.py` | [FINDINGS](FINDINGS.md) |
| Does a two-batch producer hide read/transform time? | [ONDEMAND](ONDEMAND.md), `ondemand.py prefetch` | [ONDEMAND-RESULTS](ONDEMAND-RESULTS.md): limited benefit while reads dominate |
| Does caching decoded records help? | [CACHE](CACHE.md), `ondemand.py cached` | [CACHE-RESULTS](CACHE-RESULTS.md): fewer decodes, read cost remains |
| Does a raw-page cache avoid repeated SDK reads? | [PAGES](PAGES.md), `ondemand.py pages` | [PAGES-RESULTS](PAGES-RESULTS.md): small working set fits cache |
| What happens beyond that cache, and where are reads amplified? | [AMPLIFICATION](AMPLIFICATION.md), `amplification.slurm` | [AMPLIFICATION-RESULTS](AMPLIFICATION-RESULTS.md): thrashing and approximately 9.5x selected-payload overfetch |
| Can existing APIs avoid neighboring rows? | [EXACT-RANGES](EXACT-RANGES.md), `ondemand.py exact` | [EXACT-RANGES-RESULTS](EXACT-RANGES-RESULTS.md): 89.5% less payload, approximately 1.7x faster in that comparison |
| Do native read optimizations help real training? | [COMBINED-CORE](COMBINED-CORE.md), `combined-core.slurm` | [COMBINED-CORE-RESULTS](COMBINED-CORE-RESULTS.md): approximately 6x with matching private baseline/combined builds |

Core PRs #384 and #386 have since merged. Their benchmark remains a result of
the pinned private builds, not a new PyPI release or proof for arbitrary inputs.
Do not multiply the two speedup ratios: they came from different comparisons.

## Optional preparation when a task's format is known

| Question | Contract / implementation | Measured result |
|---|---|---|
| Can preprocessing be paid before local training? | [STAGES](STAGES.md), `pipeline.py` / `local_train.py` | [STAGES-RESULTS](STAGES-RESULTS.md): fast prepared input, substantial storage expansion |
| Can overlapping prepared windows share frames? | [FRAMEBANK](FRAMEBANK.md), `framebank.py` | [FRAMEBANK-RESULTS](FRAMEBANK-RESULTS.md): smaller artifact, unchanged tensor contract |

Prepared artifacts are application outputs, not DreamDB's universal data model.
They require a known task input format and do not eliminate preparation cost.
See the [historical guide](HISTORICAL-GUIDE.md) for phase-specific commands and
the additional repack cost in the frame-bank experiment.

## Reading measurements

Distinguish source reads, decoding, tensor assembly, transfer, compute and
startup. A small fixture fitting cache is not a scale result; a completed
bounded batch is not evidence of general streaming/backpressure. Full-array
input comparisons in these runs do not establish training quality. Reuse the
existing direct checks when changing behavior; do not add validators around
the experiment machinery merely to increase an evidence count.
