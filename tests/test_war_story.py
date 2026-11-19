"""Pin the bug that drove the central design decision: offset-gap false alarms.

The first completeness check in this project counted contiguous offsets: any offset
below the watermark that was not applied was reported as a lost row. On a transactional
topic that was wrong, because a transaction commit marker consumes an offset without
carrying a row, so the detector flagged every marker as loss while nothing had been
lost. The fix was to reconcile by per-key version instead of by offset. ADR-001 records
the decision; this test makes the regression impossible to reintroduce silently.
"""

from __future__ import annotations

from cdc_audit.consumer import consume
from cdc_audit.delivery import deliver
from cdc_audit.reconcile import (
    detect_offset_gaps,
    false_alarm_offsets,
    reconcile_by_version,
)
from cdc_audit.source import generate_source


def _transactional_but_lossless():
    # Markers make the offsets sparse; a small window within the buffer loses nothing.
    source = generate_source(
        20260219, keys=300, events=1200, txn_marker_every=20, txn_marker_width=2
    )
    delivered = deliver(source, reorder_window=4, seed=20260219)
    sink = consume(delivered, skip_rule="version", commit_interval=16)
    return source, sink


def test_the_offset_gap_detector_raises_false_alarms_on_a_transactional_topic():
    source, sink = _transactional_but_lossless()
    gaps = detect_offset_gaps(source, sink)
    assert gaps.diverged_count > 0


def test_those_alarms_are_genuinely_false_no_row_was_lost():
    source, sink = _transactional_but_lossless()
    # The correct reconciler sees the sink as complete.
    assert reconcile_by_version(source, sink).clean


def test_every_flagged_gap_is_a_marker_hole_not_a_lost_record():
    source, sink = _transactional_but_lossless()
    gaps = detect_offset_gaps(source, sink)
    false_alarms = false_alarm_offsets(source, sink)
    # On a lossless transactional topic, every gap the detector raised is a false alarm.
    assert gaps.diverged_count == len(false_alarms)


def test_the_version_reconciler_never_inspects_offsets_so_markers_do_not_fool_it():
    source, sink = _transactional_but_lossless()
    assert reconcile_by_version(source, sink).diverged_count == 0
