# Reusing the reference design

The reusable part is the ownership/contract and its explicit tradeoffs, not an RL
package that other applications must adopt.

1. Define identity, clocks and event boundaries in the application first. Here
   terminal/reset are distinct and ordinal anchors are not simulation time.
   For another domain, define its own semantics; do not add them to DreamDB core.
2. Map values to public scalar/typed-array fields. Keep exact state out of lossy
   similarity embeddings. Persist required assets and shape/version metadata so
   readers do not need the original producer directory or process.
3. Choose one writer and an explicit publication boundary. Bound CPU transport,
   acknowledge only committed batches, report errors and incomplete tails. A
   bounded arena is not a bound on total RSS; a queued row is not yet durable.
4. Use projected reads and pinned snapshots. This example's scalar anchor-list
   intersection and episode materialization are adequate for the bounded example,
   not evidence of efficient selection over billions of records.
5. Verify the application's real boundary once: this recorder is compared to a
   manual-reset simulation; the PPO adapter to the trainer's own rollout; playback
   to original-model poses and actual rendering. Do not grow a test-of-test system.
6. Measure full completion cost, including drain and object/history amplification.
   Batching improved this example, but its remaining cost disqualifies it as an
   off-the-shelf large-scale recorder. Do not hide costs by dropping events or
   reading private DreamDB objects. Investigate generic storage improvements as
   ordinary DreamDB user feedback.

Before adapting to another robot/task, revisit model randomization, actuator and
mocap state, observation/action transforms, resets, partial episodes and model
portability. Before multi-node use, define application-side sharding and publication
ownership. None of those are implemented by this fixed-model, single-writer example.

The prototype has no service endpoint, plugin registry, independent release train,
retry coordinator, general checkpoint format or product roadmap. No promise of
policy convergence, deterministic action replay, arbitrary asset support, real-time
viewing, S3 performance or production-scale sustained throughput is made.
