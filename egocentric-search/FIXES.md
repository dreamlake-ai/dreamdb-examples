# #400: blocking implementation follow-up (2026-09-17)

Merged via [PR #401](https://github.com/dreamlake-ai/dreamdb-core/pull/401)
at `0ec901f0ada7050a05ec689b137c1e87e6741139`; all 14 PR checks passed.
Base was `19665f061c6077c142676b4718f47fe42b286d68`. This is not a new
PyPI release or a new S3 benchmark. The commit IDs below name the original
local changes; the PR combined them (including cherry-picked equivalents).

## Changes and direct evidence

1. **S3 If-Match 409 classification**: `8679b25` (record `64c31f9`).
   The real four-writer S3 run exposed ConditionalRequestConflict as Backend.
   The fix maps only the recognized conditional update response to CasFailed;
   reopening/retry remains the caller's responsibility. Existing real HTTP
   connector tests: **25 passed**, including unrelated/create-only refusals.
   No patched-build S3 rerun or speedup is claimed.
2. **Repeated base appends cannot merge**: `a13ac6a`.
   Released-0.0.14 reproduction: scalar x, two branches, two separate appends
   per branch, disjoint anchors. merge_many applies worker0, then rejects worker1
   as two Layers naming different exact parents. The builder confused version
   edges with Layer status, despite append preserving structural role=base.
   The fix follows the existing base/base rule: fused base, no Layer parent,
   history retained via Manifest.parents. Genuine base/Layer and differing-parent
   Layer fusion remain refused. A direct Dataset append/merge/reopen test checks
   all four anchor/value pairs. **91 create_open + 44 lineage_builder_graph tests
   passed**. The original ingest branch/merge integration test also passes with
   the patched wheel. This is not general multi-parent Layer fusion support.
3. **Python VideoItem write gap**: `fdd0a3a`.
   Adds Schema.add_video_item and Dataset.publish_prepared_video_item, directly
   wrapping core. Per-item init/relative fragments, opaque keys and exact u64
   times are preserved. Reusing a key replaces an item; no implicit retry,
   transcode, preview or streaming. Direct Python create/publish/reopen/range-read
   checks init/fragment bytes, independent placement, replacement and invalid-init
   refusal. API baseline/anchor table updated for the intended additions.
   Installed-wheel selection: **389 passed, 1 existing skip**.

## Reproduce

Combine the above commits on the base. The checks ran in an isolated local
container using `ddb-testbox:1.97.0-7d7c440db3b8`, Rust 1.97.0, four Cargo jobs,
8 CPUs and a 20 GiB ceiling. This is Linux **preflight in the testbox image**,
not the bound `testbox run` Evidence workflow or CI. No mutation matrix added.
Clippy completed without errors but with existing warnings.

Capture output and actual exit codes, without output-filter pipelines:

```sh
cargo test -p dreamdb-connector-http --test connector_e2e
cargo test -p dreamdb-protocol --test lineage_builder_graph
cargo test -p dreamdb-dataset --test create_open
cd dreamdb-dataset-python
maturin build --interpreter /path/to/venv/bin/python --out /path/to/wheels
# Install the exact emitted wheel into that venv, then:
python -m pytest -q tests/test_video_item_read_api.py tests/test_video_item_write_api.py tests/test_api_parity.py tests/test_anchor_mutation.py
```

In ingest commit `270e174`, with that wheel and numpy:
`PYTHONPATH=. python -m pytest -q -m integration tests/integration/test_end_to_end.py::test_branch_and_merge_round_trip`.

Initial Python wiring failures were corrected at their own layer: use an
installed wheel instead of editable installation; add new time parameters to
the existing table. No assertion was relaxed. An assumed wheel filename was
corrected to the filename actually emitted by maturin.

This fixture proves SDK publication/readback, not browser playback or real
HEVC remux/decode preservation. Next: integrate the writer into the original-only
segmented adapter, then the bounded real-data pilot and patched S3 concurrency
case. No new remote data writes or CI were launched here.
