# ADR-004: Last-writer-wins as the correctness oracle, and what it cannot see

Status: accepted

## Context

The reconciler needs a definition of "correct" for a key. A CDC sink is a materialised table: for
each key it holds the current row. The natural oracle is therefore the newest write the source holds
for that key, by per-key version. Comparing the sink's value for a key against that newest write is
last-writer-wins (LWW) reconciliation.

LWW has a consequence that must be stated rather than hidden. If a write is lost but a later write to
the same key would have overwritten it anyway, the steady-state value is still correct, so LWW does
not count it as a divergence. On the shipped stream this is exactly why 153 records were dropped but
only 40 keys end up wrong: 113 of those drops were intermediate writes that a later write superseded.

## Decision

Use **last-writer-wins by per-key version** as the correctness oracle. A key is divergent only when
its final materialised value in the sink differs from the final value the source dictates. A lost
intermediate write that does not change the final value is, by this definition, not a divergence.

## Alternatives considered

- **Full operation-sequence replay.** Treat the sink as wrong if any single change was dropped, even
  one later overwritten. Rejected for a materialised-table sink: it would flag the 113 harmless drops
  as failures, conflating "the table is wrong" with "an intermediate event was lost", which is a
  different and usually less important property.
- **Count dropped records as the headline.** Rejected for the same reason: the record count
  overstates harm exactly as badly as the watermark understates it. The record count is kept as
  context in the report, with keys-diverged as the verdict.

## Consequences

- The tool answers "is the current table correct", which is the right question for a materialised
  sink. It does not answer "was every intermediate state delivered", which matters for an event log
  or an audit trail. A system that needs the latter needs a different oracle, and the README says so.
- The gap between records dropped (153) and keys diverged (40) is itself a result worth publishing,
  because it shows why neither the watermark nor a naive drop count is the right number.
- Deletes are modelled as tombstones so that "should be absent" is a distinct expected state from
  "should hold value V", and a key that lingers after a delete is counted as stale rather than
  silently passing.
