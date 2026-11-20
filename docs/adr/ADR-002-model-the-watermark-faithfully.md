# ADR-002: Model the max-applied-offset watermark faithfully, rather than fixing it

Status: accepted

## Context

The consumer in this project commits a watermark and deduplicates incoming records by offset: a
record at or below the committed watermark is treated as already applied and skipped. That rule is
the source of the interior loss the tool exists to expose. It would be easy to replace it with a
correct rule and ship a consumer that never loses anything.

That would defeat the purpose. The project is not a better consumer; it is an audit that shows what
a widely deployed consumer design hides. If the modelled consumer did not have the blind spot, there
would be nothing to detect and nothing to measure.

## Decision

Model the offset-deduplicating consumer and the max-applied-offset watermark **faithfully**, as a
component under test, and leave the correct behaviour available only as the contrast (`skip_rule =
"version"`) used to show that the same stream reconciles cleanly under the right rule. The tool's
value is in the reconciler that sits beside the watermark, not in changing the watermark.

## Alternatives considered

- **Ship a fixed consumer that commits a contiguous frontier.** Rejected as the main artefact: it is
  a real and good design, but it removes the phenomenon the tool measures. It is effectively what the
  version skip rule demonstrates, kept as a one-line contrast rather than the headline.
- **Model the watermark as the contiguous frontier from the start.** Rejected: a contiguous-frontier
  watermark never skips an unapplied record, so lag and completeness would always agree and the
  project would have no subject.

## Consequences

- The shipped scenario deliberately exhibits loss. The verdict on it is "exactly-once violated",
  which is the intended demonstration, not a defect.
- A reader could mistake the modelled consumer for a recommendation. The README and this ADR state
  plainly that it is a faithful model of a flawed-but-common design, held up for inspection.
- Because the watermark is modelled in isolation, in `watermark.py`, with no access to keys or
  versions, the blind spot is a property of the metric rather than of a careless implementation. That
  is what makes the result generalise beyond this code.
