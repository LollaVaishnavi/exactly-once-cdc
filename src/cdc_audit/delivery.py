"""Model bounded out-of-order delivery, deterministically from a seed.

Why this file exists: exactly-once is not threatened by delivery alone. It is
threatened by the interaction between reordered delivery and a consumer that
commits a watermark and then skips anything at or below it. This module supplies
the reordering half of that interaction, with a displacement that is provably
bounded so the scenario stays honest about how far an event can slip.

The reorder is produced by giving each event a jittered delivery time
`position + j` with j drawn in [0, reorder_window], then stable-sorting by that
time. An event can therefore be overtaken by at most reorder_window later events
and can jump ahead by at most reorder_window positions, so the maximum
displacement equals reorder_window. No event is dropped here; loss is the
consumer's doing, not the channel's.
"""

from __future__ import annotations

import random

from cdc_audit.model import ChangeEvent, SourceLog


def deliver(source: SourceLog, *, reorder_window: int, seed: int) -> tuple[ChangeEvent, ...]:
    """Return the events in the order the consumer receives them.

    reorder_window is a count of positions, not a duration, so the delivery order
    is identical on every machine. A window of zero returns the events in source
    order unchanged.
    """
    if reorder_window < 0:
        raise ValueError("reorder_window must not be negative")
    events = source.events
    if reorder_window == 0:
        return events

    rng = random.Random(seed ^ 0x5CDC)
    jittered = [
        (position + rng.randint(0, reorder_window), position, event)
        for position, event in enumerate(events)
    ]
    # Stable sort: ties keep source order, so displacement stays bounded by window.
    jittered.sort(key=lambda triple: (triple[0], triple[1]))
    return tuple(triple[2] for triple in jittered)


def max_displacement(source: SourceLog, delivered: tuple[ChangeEvent, ...]) -> int:
    """How far, in positions, the most-displaced event moved from its source slot.

    Used by a test to confirm the channel never exceeds the declared window, so a
    reader can trust that the loss shown is interior reorder loss and not the
    channel quietly throwing events arbitrarily far.
    """
    source_pos = {event.offset: i for i, event in enumerate(source.events)}
    worst = 0
    for delivered_pos, event in enumerate(delivered):
        worst = max(worst, abs(delivered_pos - source_pos[event.offset]))
    return worst
