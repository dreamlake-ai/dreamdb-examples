# On-demand raw-data training prototype

## Claim and boundary

Can a bounded producer overlap native DreamDB PNG/sensor selection and task-time
conversion with real GPU training, reducing consumer wait without a ready artifact?
This is an application reference, not a new DreamDB loader API. Source remains
the pinned capture; four-frame float32 layout is selected by this task at read time.
No persistent transformed data or cross-batch cache is used.

Observable failures: different inputs/order, missing producer errors, unbounded
queued batches, or slower real loop despite lower apparent wait. Minimum evidence
is the actual training boundary: compare each delivered batch with capture witnesses,
run identical optimizer work, and measure completed operations. No secondary test
framework or synthetic GPU sleep.

## Design

Serial Reader versus a spawned process owning its own Reader. Queue capacity two;
at most two queued batches plus one producer batch and one consumer batch. This
bounds batch payload, not SDK internals or total RSS. Existing bounded capture and
32-row projected reads remain unchanged. Producer exceptions reach the consumer;
timeouts and finally termination prevent an orphan producer.

Use the same seed, two epochs, shuffled requests, model, transforms and batch size.
Measure producer read/conversion, consumer wait, completed H2D, completed compute,
loop elapsed, startup/first batch, and separate process peak RSS. Exact witness
comparisons occur at delivered batch boundary and their time is separately reported.
Results describe this small warm local backend, not remote IO, steady-state large
datasets, or arbitrary task formats. Multiprocessing copies are part of the cost.

## Implementation and execution plan

1. Add an isolated on-demand CLI reusing capture, Reader and model; no core edits.
2. Check syntax locally, then run real capture and both modes in separate processes
   in a bounded Slurm GPU allocation. Run serial/prefetch then reverse order to
   expose simple ordering effects; no benchmark sweep.
3. Record concise results and limitations, open a stacked example PR, clean task
   source/runtime/scratch after preserving code and reproduction instructions.

No fixed-ready artifact is constructed. A producer slower than the GPU cannot be
hidden by queue depth; a negative result should identify that next boundary instead
of expanding concurrency, caching, and storage changes in the same experiment.
