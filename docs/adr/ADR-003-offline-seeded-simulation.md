# ADR-003: An offline seeded simulation instead of an embedded Kafka

Status: accepted

## Context

The subject matter is Kafka and stream processing, so the realistic choice would be to run a real
broker in tests, produce to a transactional topic, and consume it. Testcontainers or an embedded
broker would make that possible.

The cost is reproducibility. A reviewer who clones the repository would need Docker, a JVM, image
pulls over the network, and several seconds of broker startup per run, and the numbers would move
slightly from run to run with timing and partitioning. The whole credibility of this project rests
on a reviewer reproducing every published figure with one command, so anything that makes a figure
move between runs is a direct cost to the thing the project is selling.

## Decision

Model the pipeline **offline and deterministically** in pure Python. A seeded generator builds the
changelog, a seeded bounded-reorder function stands in for the channel, and a plain consumer applies
the stream. No broker, no JVM, no network, no credentials. `make verify` runs from a fresh clone
with nothing installed beyond the standard library and reproduces every number, byte for byte, on
re-run.

This is the boring choice, and it is the right one here.

## Alternatives considered

- **Testcontainers with a real Kafka.** Rejected for `make verify`: it trades reproducibility for a
  realism the project does not need, because the failure mode being demonstrated (offset contiguity
  breaking on markers and reorder) is a property of offsets, not of the broker. It belongs in an
  integration lane outside verify, listed as future work.
- **Record and replay a captured broker trace.** Rejected: a captured trace is opaque, cannot be
  reconfigured by a reviewer, and still needs the broker once to capture.

## Consequences

- The reorder model is synthetic. Its arrival-time distribution differs from real consumer
  rebalances and producer retries. The offset-contiguity failure mode is identical, which is the only
  property the tool measures, so the simplification does not weaken the result. The README states this
  boundary.
- A real transactional source adapter, validated against a broker, is future work with a named first
  metric: the version reconciler's false-alarm count on a real topic, which should stay at zero.
- Determinism is enforced, not hoped for: a test reconciles two independent runs of the shipped
  scenario and asserts the sinks are identical.
