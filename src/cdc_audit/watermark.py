"""The watermark view: exactly what a consumer-lag dashboard reports, and no more.

Why this file exists: the project's claim is precise, so the thing it is measured
against has to be modelled precisely too, in isolation, with nothing borrowed from
the source changelog. Consumer lag is the source's high offset minus the committed
watermark. That single subtraction is the entire information a lag dashboard has.
Keeping it here, unable to see keys or versions, is what makes the blind spot a
property of the metric rather than of a sloppy implementation.
"""

from __future__ import annotations

from cdc_audit.model import SinkState, SourceLog


def watermark_lag(source: SourceLog, sink: SinkState) -> int:
    """Lag in offsets: how far the committed watermark trails the source high offset.

    Zero means the dashboard shows the consumer fully caught up. It says nothing
    about whether every row below the watermark was actually applied, which is the
    whole point.
    """
    return source.max_offset - sink.committed_watermark
