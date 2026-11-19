"""The consumer that applies a delivered stream and commits a watermark.

Why this file exists: this is the component whose faithful-but-wrong behaviour the
whole project exists to expose.

A real consumer tolerates some reordering before it commits. It buffers a bounded
number of in-flight records, applies them in offset order, and commits a watermark
as the offset frontier advances. The buffer capacity is the amount of reordering it
can absorb. The common idempotency rule then dedupes by offset: any record whose
offset is at or below the committed watermark is assumed already applied and is
skipped.

That rule is correct for a genuine duplicate and silently wrong for a record that
was displaced backward further than the buffer could hold: such a record is released
after the frontier has already passed its offset, so it is dropped though it was
never applied. The displacement needed for that is exactly one position more than the
buffer capacity, which is why interior loss appears only when the reorder window
exceeds the commit interval. Both rules live here so the contrast is measured.
"""

from __future__ import annotations

import heapq

from cdc_audit.model import DELETE, ChangeEvent, SinkState


def _apply(sink: SinkState, event: ChangeEvent) -> None:
    """Materialise one change into the sink and record that its offset was applied."""
    if event.op == DELETE:
        sink.values.pop(event.key, None)
    else:
        sink.values[event.key] = event.value
    sink.applied_offsets.add(event.offset)
    prior = sink.applied_lsn_by_key.get(event.key, 0)
    if event.lsn > prior:
        sink.applied_lsn_by_key[event.key] = event.lsn


def _emit(sink: SinkState, event: ChangeEvent, skip_rule: str) -> None:
    """Handle one record leaving the reorder buffer, applying the skip rule.

    Under the offset rule a record at or below the committed watermark is dropped as
    a presumed duplicate. Under the version rule only an already-applied per-key
    version is dropped, so a late record is still applied and nothing is lost.
    """
    if skip_rule == "offset":
        if event.offset <= sink.committed_watermark:
            return  # presumed duplicate; this is where interior loss happens
        _apply(sink, event)
        sink.committed_watermark = event.offset
    else:
        if event.lsn <= sink.applied_lsn_by_key.get(event.key, 0):
            return  # genuine duplicate by per-key version
        _apply(sink, event)
        sink.committed_watermark = max(sink.committed_watermark, event.offset)


def consume(
    delivered: tuple[ChangeEvent, ...],
    *,
    skip_rule: str,
    commit_interval: int,
) -> SinkState:
    """Run the delivered stream through a bounded reorder buffer and return the sink.

    commit_interval is the buffer capacity: the number of records the consumer holds
    and reorders by offset before releasing the smallest. A record displaced backward
    by more than this many positions is released out of order, and under the offset
    skip rule it is then dropped. skip_rule "version" dedupes by per-key lsn and loses
    nothing.
    """
    if skip_rule not in ("offset", "version"):
        raise ValueError("skip_rule must be 'offset' or 'version'")
    if commit_interval < 1:
        raise ValueError("commit_interval must be at least 1")

    sink = SinkState()
    buffer: list[tuple[int, int, ChangeEvent]] = []

    # counter is a tie-breaker so the heap never has to compare ChangeEvent objects
    # when two records share an offset (they never do here, but the heap cannot know).
    for counter, event in enumerate(delivered):
        heapq.heappush(buffer, (event.offset, counter, event))
        if len(buffer) > commit_interval:
            _, _, out = heapq.heappop(buffer)
            _emit(sink, out, skip_rule)

    # Drain the buffer in offset order at shutdown.
    while buffer:
        _, _, out = heapq.heappop(buffer)
        _emit(sink, out, skip_rule)

    return sink
