# Application-oriented repository organization

See [the contract](EXAMPLE-CONTRACT.md). This is the implementation plan for
the repository organization, not a new application milestone.

## Design

- Root README is a scenario catalog and starting point, not an experiment log.
- Keep existing top-level application directories and Python paths. Moving
  LLFF folders would break sibling/shared-helper imports; moving training
  scripts would break recorded reproduction commands without user benefit.
- Give multimodal training a short current README and an experiment index;
  retain its former long guide as explicitly historical documentation.
- Keep mjlab's detailed working instructions, adding concise navigation and
  current source-versus-package status.
- Preserve older LLFF examples as clearly labeled legacy/companion material;
  updating their SDK integration is a separate implementation task.
- Add a contribution guide and a README-only template. No common dependency
  bundle, application registry, launcher, plugin system or new CI framework.

## Sequence and acceptance

1. Inventory existing READMEs, imports, dependency pins and CLI entry points.
2. Publish the scenario catalog and contribution/template contract.
3. Separate usage/navigation from experimental results and mark legacy status.
4. Resolve changed Markdown's local file links and inspect command names
   against existing entry points. Confirm executable files are unchanged.
5. Submit a documentation PR and remove the temporary worktree after push.

The claim is navigability and honest scope, not renewed runtime compatibility.
Do not rerun GPU experiments or full CI to validate unchanged executable code.

## Outcome (2026-09-17)

The catalog, application entry points, experiment map, contribution guide and
README template are in place. Script locations and dependency pins are unchanged.
The former multimodal README is retained as `HISTORICAL-GUIDE.md` in the same
directory, preserving its relative links and phase-specific instructions.

Source inspection also corrected the Rerun README's nonexistent DreamDB backend
mode: its actual converter uses local LLFF, Rerun and LanceDB. The legacy
LanceDB product-comparison table was removed rather than treated as current.

One direct documentation check resolved all 75 local Markdown file links with
zero missing targets; external URLs and heading fragments were not validated.
Run/capture/preflight/exact commands and the Rerun CLI were checked against
their existing source entry points. Executable code is unchanged. No runtime,
GPU or package-compatibility revalidation is claimed for this organization PR.
