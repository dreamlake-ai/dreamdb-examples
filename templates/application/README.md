# Application name — replace before contributing

This is a documentation template, not a runnable application. Replace every
placeholder; do not leave invented commands or validation claims in a PR.

## Purpose and status

Describe the user problem, input and output. Choose a status: validated
reference, experimental, legacy/unverified, or companion. State the exact
validated scope, if any; this label is not a production-readiness guarantee.

## Why DreamDB / what the application owns

Name the public storage/query/snapshot capabilities used. Separately describe
the domain model, transformations and workflow defined by the application.
Explain what another application can reuse without adopting your domain.

## Requirements

List the tested DreamDB package version or source commit, local dependency
file, language/runtime, optional hardware/services and configuration method.
Distinguish private benchmark builds from released packages. No credentials.

## Smallest run

Provide actual setup/run commands after implementing them. Name their working
directory, required input and observable output. Explain whether data is
generated, supplied by the user or downloaded, and whether writes occur.

## Design and optional workflows

Link to the application's data contract, design and optional workflows using
real relative paths. Keep historical alternatives in a separate experiment
index rather than turning this README into a chronological log.

## Validation and limitations

State the direct behavior checked, fixture size, environment and expected
failure signal. Record performance only when measured, including costs and
limits. Explicitly name untested modes; do not invent a validation framework.

## Outputs and cleanup

List generated data, environments and other artifacts. Explain what is removed
automatically, what remains and how users remove their own task artifacts
without deleting unrelated data. Keep private data and large raw logs out of Git.
