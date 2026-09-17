# Adding an external application

Follow the [example contract](docs/EXAMPLE-CONTRACT.md). Begin with an issue
describing the user problem, then a small contract/design and implementation
plan. Keep scope at a reference implementation, not an independently evolving
product. A useful example can be retrieval, annotation, visualization, data
processing or another domain; it need not involve robotics or training.

## Directory and dependencies

Use a descriptive top-level directory and copy the
[README template](templates/application/README.md) into it. Keep the application
code, its dependency declarations and smallest runnable check nearby. Prefer
an independently understandable example over a shared base class or plugin API.
Only introduce shared utilities when concrete consumers justify them.

Do not add all application dependencies to a root environment. Record tested
versions, optional hardware/services and how configuration is supplied. Use
public DreamDB interfaces; distinguish released packages from source builds.
Never claim current compatibility merely because an old command still exists.

## Data and evidence

Document what each record means, how snapshots and identity are chosen, and
which decisions belong to the application rather than DreamDB. Supply a tiny
generated fixture or instructions to acquire permitted public data. Keep real
private data and credentials out of the repository.

State the observable application claim and use the smallest direct check that
can falsify it. Report measured workload/environment and limitations. Do not
build an audit/mutation framework around the example or rerun expensive GPU
and CI workloads for navigation-only documentation changes.

Put alternative strategies and historical measurements behind an experiment
index; keep the application README focused on what a new user should run.
Preserve failed hypotheses when they explain a tradeoff, not redundant raw logs.

## Ready for review

- Root catalog links to the application with an honest status.
- README identifies input, output, DreamDB responsibilities, dependencies,
  runnable commands, an observable success criterion and limitations.
- Results name the tested SDK/source and do not imply production readiness.
- Generated data and task-specific environments/builds are cleaned, or exact
  retained locations and reasons are recorded. No deletion of user data.
- Existing examples, imports and reproduction commands are not silently broken.

There is no requirement to create a new CI framework. Use the application's
existing execution boundary; changes to DreamDB itself belong in the core repo.
