"""Reconcile a sink against the source, by the correct method and by the naive one.

Why this file exists: this is what the watermark cannot do. Two reconcilers live
here so the trade-off is measured, not claimed.

  reconcile_by_version needs the source changelog and compares the sink's
  materialised value per key against last-writer-wins truth. It is correct: it
  catches interior loss and never fires on a legitimately sparse offset space. It
  costs O(keys) memory for the per-key truth, and it is only as good as the source
  log it is given.

  detect_offset_gaps is given only what a lag-style monitor has: the set of applied
  offsets and the committed watermark. It flags every offset below the watermark
  that was not applied. It is cheap, needs no changelog, and cannot tell a lost row
  from a transaction marker, so it raises false alarms on exactly the topics most
  likely to use exactly-once in the first place.

The sampling knob on the version reconciler models a memory-bounded deployment:
inspecting only a fraction of keys introduces a detection floor, quantified in
experiment D, below which a small loss can pass unseen.
"""

from __future__ import annotations

import random

from cdc_audit.model import UPSERT, ReconcileResult, SinkState, SourceLog


def _low_offset(sink: SinkState) -> int:
    """The lowest applied offset, or zero when nothing was applied.

    Both gap routines scan upward from here to the watermark, so they share one
    definition of where the scan starts rather than risking two that drift apart.
    """
    return min(sink.applied_offsets) if sink.applied_offsets else 0


def _materialised_expected(source: SourceLog) -> dict[str, str | None]:
    """The value each key should hold in the sink: the latest upsert, or None if deleted."""
    expected: dict[str, str | None] = {}
    for key, event in source.latest_by_key().items():
        expected[key] = event.value if event.op == UPSERT else None
    return expected


def reconcile_by_version(
    source: SourceLog,
    sink: SinkState,
    *,
    sample_fraction: float = 1.0,
    seed: int = 0,
) -> ReconcileResult:
    """Compare sink against last-writer-wins truth, optionally sampling keys.

    A key diverges when its materialised value in the sink differs from what the
    source says it should be. A lost intermediate write that a later write would
    have overwritten anyway is deliberately not a divergence, because the steady
    -state value is still correct; that boundary is stated in ADR-004.
    """
    if not 0.0 < sample_fraction <= 1.0:
        raise ValueError("sample_fraction must be in (0, 1]")

    expected = _materialised_expected(source)
    all_keys = sorted(expected)
    if sample_fraction >= 1.0:
        keys_to_check = all_keys
    else:
        rng = random.Random(seed ^ 0xA17E)
        sample_size = max(1, int(round(len(all_keys) * sample_fraction)))
        keys_to_check = sorted(rng.sample(all_keys, sample_size))

    missing: list[str] = []
    stale: list[str] = []
    for key in keys_to_check:
        want = expected[key]
        have = sink.values.get(key)
        if have == want:
            continue
        if want is not None and have is None:
            missing.append(key)
        else:
            # Wrong value present, or a value that should have been deleted.
            stale.append(key)

    diverged = tuple(sorted(missing + stale))
    return ReconcileResult(
        source_max_offset=source.max_offset,
        committed_watermark=sink.committed_watermark,
        watermark_lag=source.max_offset - sink.committed_watermark,
        diverged_keys=diverged,
        missing_keys=tuple(sorted(missing)),
        stale_keys=tuple(sorted(stale)),
        method="version",
        keys_checked=len(keys_to_check),
        keys_total=len(all_keys),
    )


def detect_offset_gaps(source: SourceLog, sink: SinkState) -> ReconcileResult:
    """Flag every unapplied offset below the committed watermark, naming nothing.

    The detector is given the source only to size the key universe for the result;
    its decision uses solely applied_offsets and the watermark, which is all a
    lag-style monitor has. It cannot distinguish a lost row from a control-record
    hole, so each gap is reported as the opaque label "offset:N". The companion
    experiment cross-references the source to count how many of those were false
    alarms.
    """
    low = _low_offset(sink)
    gaps = [
        n for n in range(low, sink.committed_watermark + 1) if n not in sink.applied_offsets
    ]
    labels = tuple(f"offset:{n}" for n in gaps)
    return ReconcileResult(
        source_max_offset=source.max_offset,
        committed_watermark=sink.committed_watermark,
        watermark_lag=source.max_offset - sink.committed_watermark,
        diverged_keys=labels,
        missing_keys=labels,
        stale_keys=(),
        method="offset_gap",
        keys_checked=len(gaps),
        keys_total=len(source.keys),
    )


def false_alarm_offsets(source: SourceLog, sink: SinkState) -> tuple[int, ...]:
    """Offsets the gap detector flags that carry no source record: pure false alarms.

    An offset below the watermark that is neither applied nor present in the source
    log is a transaction-marker or compaction hole. The gap detector flags it; the
    version reconciler never does.
    """
    source_offsets = {event.offset for event in source.events}
    low = _low_offset(sink)
    return tuple(
        n
        for n in range(low, sink.committed_watermark + 1)
        if n not in sink.applied_offsets and n not in source_offsets
    )
