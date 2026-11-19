"""cdc_audit: detect exactly-once violations a consumer-lag watermark cannot see.

The public surface is deliberately small. A caller builds a source changelog,
runs it through a delivery model and a consumer to get a sink, then reconciles
the sink against the source. Everything is pure-Python and deterministic from a
seed so the same inputs produce the same sink and the same verdict on any
machine.
"""

from cdc_audit.model import ChangeEvent, ReconcileResult, SinkState, SourceLog

__all__ = ["ChangeEvent", "SourceLog", "SinkState", "ReconcileResult"]
__version__ = "0.1.0"
