# ADR-005: Sampled reconciliation and its detection floor

Status: accepted

## Context

Full reconciliation holds the newest version of every key, which is O(keys) memory. A large keyspace
can make that expensive, and the tempting economy is to inspect only a fraction of keys. That works
on average and fails in the specific way that matters: a loss confined to a few keys can fall
entirely outside the sample and pass unseen.

The question is not whether to offer sampling but whether its cost can be stated exactly, so that a
sampled verdict is never mistaken for a full one.

## Decision

Offer **sampled reconciliation** behind a `sample_fraction` policy knob, and publish its detection
floor as an exact probability next to the method. For a loss of L keys out of K, inspecting a sample
of s keys misses the loss entirely with probability C(K-L, s) / C(K, s). Experiment D computes this
in closed form and, when numpy is available, cross-checks it with a seeded Monte Carlo that is
printed but never published, so the headline stays deterministic.

## Alternatives considered

- **Always reconcile fully.** Rejected as the only option: it is the safe default (and is the
  default, `sample_fraction = 1.0`), but refusing to model the bounded-memory case would leave the
  most likely real-world compromise unanalysed.
- **A probabilistic sketch (Bloom or HyperLogLog style) instead of a sample.** Rejected for now as
  added complexity without a measured benefit; it is named in future work with its own first metric,
  the detection floor at a fixed memory budget compared against the exact floor here.

## Consequences

- A sampled run reports how many keys it checked against the total, so the verdict is never read as
  exhaustive when it was not.
- The floor is uncomfortable and that is the point: sampling 10% of keys misses a single lost key
  90% of the time, and catching a single-key loss with 95% confidence needs 95% of the keys. Sampling
  buys memory and spends detection, priced in a probability rather than a reassurance.
- The default path remains full and deterministic, so the published headline numbers do not depend on
  a sample seed.
