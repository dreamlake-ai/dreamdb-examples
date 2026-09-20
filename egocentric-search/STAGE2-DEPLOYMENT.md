# Stage 2: core merge and qualified SDK artifact

2026-09-20. This page records the merge of both pre-ingest capability gates and
the SDK artifact qualified from that source. It is a provenance record, not a
readiness claim: no stage-2 data job has been admitted or submitted, and
[core #400](https://github.com/dreamlake-ai/dreamdb-core/issues/400) remains
open. See [STAGE2-PLAN.md](STAGE2-PLAN.md) for the budget envelope and the
remaining unfinished work.

## Merged source

Core PR 408 is merged as `b0f0e407438d4a6bbac9d3142cd257a21bd3ad2a`, with
parents `f2c33fe` and `c93ca1af243221329f58ba34f057b54e99043f48`. The merge
commit's tree is `6d54e258ab99a281c05fbe49535b3f9cfa0718f9`, identical to
`c93ca1a`'s tree, so the merge introduced no content of its own. The branch
carried the HTTP connector request telemetry and the interleaved ingest
provenance check described in STAGE2-PLAN.md. The private leaf patch from base
`cd71b1a` is now merged. All 14 checks reported on the PR passed, including
`cargo test` 14m4s, WASM release artifacts 10m34s, python bindings 5m27s and the
aarch64 wheel 6m34s; Main integrity run 35489563728 passed on the merge commit.
Which of those checks are formally *required* is not established here.

The registry 0.0.15 artifact is **unchanged**: nothing was published to PyPI or
npm as part of this merge.

Adapter PR 28 in `dreamlake-ai/dreamlake-ingest` — the bounded stage-two
producer/publisher bridge with durable epoch receipts — is merged as
`a4d71664c3eb68920e61e8274d06c3d95a00d87f`, whose tree
`98746e25481c7539f6bf84458a24345ba3da52b9` is identical to that of its head
`18933a320ffdd3ef8f99620a551f82bf066ed997`.

## Qualified artifact

CPU build Slurm 148490 COMPLETED, exit 0:0, runtime 1:03. It built core
`c93ca1af243221329f58ba34f057b54e99043f48` — the truthful compiled revision,
deliberately recorded instead of the merge SHA — producing wheel 0.0.15 with
digest `e9d5e2060f50d6ce4f4bef52827eafa9a6f376ac0b68a037928cb2bf4b48c52a`.

Runtime preflight Slurm 148492 COMPLETED, exit 0:0, runtime 4s, in a private
venv installed from that wheel. It read back the actual writer revision
`c93ca1a`/`build custom`, then ran HTTP 2 passed in 0.13 s and ingest 4 passed
in 1.53 s, importing from
`/home/tom/ddb-ego100k-400/releases/c93ca1a-18933a3/sdk/lib/python3.12/site-packages/dreamdb`.
Adapter source under that release directory is at `18933a3`. The exact artifact
record is the run's `qualification.json`.

The preflight ran on node 099 with pytest 9.1.1, NumPy 2.2.6 and Python 3.12.3.
The script does not pin pytest, so those are observed versions for this run, not
a promise about future runs.

Resource note: 8 and 4 CPUs were requested, but actual `AllocTRES` was 32 CPUs
for both jobs; no GPU was allocated. Neither job downloaded S3 data, source
media or models — package build dependencies only.

## Deployment selection

`/home/tom/ddb-ego100k-400/releases/next-ingest` is a symlink, confirmed by the
lead to resolve to `c93ca1a-18933a3`. That selects the SDK artifact and adapter
source for the next job. It starts nothing: no job has been submitted.

## State deliberately unchanged

No ingest ran, no **corpus** Ref was written, and the shared venv was not
modified. The preflight's own local fixtures did write, as those tests require. The
old root/repo, the stage-1 journal, and the stage-1 source/media/vector
artifacts are unchanged. Stage-1 historical pins are retained intentionally;
earlier reports on the sibling pages describe their own runs and stand as
written.

The journal must adopt from `cd71b1a` at a clean boundary before the first
future ingest. That adoption has **not** been performed and the journal has not
been advanced by this work.

## Not claimed

Qualification covers artifact provenance and a focused runtime preflight. It
does not establish full stage-2 readiness. The stage-2 epoch driver, source
admission, and the wiring of connector telemetry into before/after quiescent
deltas all remain future work. No throughput, cost or recall claim follows from
this page.

Local cleanup is done: the core HTTP worktree was removed with
`git worktree remove` (no `--force`), along with three scratch files from this
PR's own work. The handoff and bench worktrees are retained because stage 2
still needs them.

Remote build cleanup is done, independently verified by the lead: CPU job Slurm
148493 COMPLETED, exit 0:0, runtime 5s, no GPU. It removed exactly the new
`core-c93…/target` (1,987,857,353 B) and `core-c93…/build-env` (86,513,675 B).
The exact reader, 22,805,304 B, was preserved by copying it to
`bin/dump_exact_subset` with an unchanged SHA256
`546a4cc8713b90034287960ec33e36737fd4e70e53f1290b181b457d55165543`. So roughly
2 GB of build directories were removed; that is **not** the exact disk space
freed, because the reader was copied out rather than deleted. The qualified
`release/sdk`, its repo and `qualification.json`, the sources, the wheel and the
reader are kept. The old SDK and all stage-1 artifacts are unchanged. Retained
data is tracked with the rest of the run in [PROGRESS.md](PROGRESS.md).

## Corrected process error

The PR 408 body contained the negative phrase "not close #400", whose bare
issue reference was parsed as a closing keyword and automatically closed the
issue. The issue was immediately reopened and the body fixed by removing the
closing reference. No data, artifact or validation consequence followed, and no
extra validation framework was introduced. Later PRs referencing #400 use plain
`Refs` wording for this reason.
