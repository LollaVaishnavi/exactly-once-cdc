"""Properties of reconciliation: version is correct, offset-gap is cheap and wrong."""

from __future__ import annotations

import pytest

from cdc_audit.model import DELETE, UPSERT, ChangeEvent, SinkState, SourceLog
from cdc_audit.reconcile import (
    detect_offset_gaps,
    false_alarm_offsets,
    reconcile_by_version,
)


def _log(*events: ChangeEvent) -> SourceLog:
    return SourceLog(events=events)


def _up(offset, key, lsn, value):
    return ChangeEvent(offset=offset, key=key, lsn=lsn, op=UPSERT, value=value)


def test_a_sink_matching_the_source_diverges_on_no_keys():
    log = _log(_up(0, "a", 1, "v1"), _up(1, "b", 1, "w1"))
    sink = SinkState(
        values={"a": "v1", "b": "w1"},
        applied_offsets={0, 1},
        applied_lsn_by_key={"a": 1, "b": 1},
        committed_watermark=1,
    )
    assert reconcile_by_version(log, sink).clean


def test_an_absent_key_that_should_exist_is_counted_as_missing():
    log = _log(_up(0, "a", 1, "v1"), _up(1, "b", 1, "w1"))
    sink = SinkState(values={"a": "v1"}, applied_offsets={0}, committed_watermark=1)
    result = reconcile_by_version(log, sink)
    assert result.missing_keys == ("b",)
    assert result.stale_keys == ()


def test_a_wrong_value_in_the_sink_is_counted_as_stale():
    log = _log(_up(0, "a", 1, "v1"), _up(1, "a", 2, "v2"))
    sink = SinkState(values={"a": "v1"}, applied_offsets={0}, committed_watermark=1)
    result = reconcile_by_version(log, sink)
    assert result.stale_keys == ("a",)
    assert result.missing_keys == ()


def test_a_key_that_should_be_deleted_but_remains_is_counted_as_stale():
    log = _log(_up(0, "a", 1, "v1"), ChangeEvent(offset=1, key="a", lsn=2, op=DELETE, value=None))
    sink = SinkState(values={"a": "v1"}, applied_offsets={0}, committed_watermark=1)
    result = reconcile_by_version(log, sink)
    assert result.stale_keys == ("a",)


def test_a_lost_intermediate_write_later_overwritten_is_not_a_divergence():
    # lsn 2 was dropped, but lsn 3 (the latest) was applied, so the steady state is correct.
    log = _log(_up(0, "a", 1, "v1"), _up(1, "a", 2, "v2"), _up(2, "a", 3, "v3"))
    sink = SinkState(
        values={"a": "v3"},
        applied_offsets={0, 2},
        applied_lsn_by_key={"a": 3},
        committed_watermark=2,
    )
    assert reconcile_by_version(log, sink).clean


def test_an_invalid_sample_fraction_is_refused():
    log = _log(_up(0, "a", 1, "v1"))
    with pytest.raises(ValueError, match="sample_fraction"):
        reconcile_by_version(log, SinkState(), sample_fraction=1.5)


def test_full_reconciliation_checks_every_key():
    log = _log(*[_up(i, f"k{i}", 1, "v") for i in range(10)])
    sink = SinkState(values={f"k{i}": "v" for i in range(10)}, committed_watermark=9)
    result = reconcile_by_version(log, sink, sample_fraction=1.0)
    assert result.keys_checked == 10
    assert result.keys_total == 10


def test_sampling_checks_a_subset_and_is_deterministic():
    log = _log(*[_up(i, f"k{i:03d}", 1, "v") for i in range(100)])
    sink = SinkState(values={f"k{i:03d}": "v" for i in range(100)}, committed_watermark=99)
    a = reconcile_by_version(log, sink, sample_fraction=0.3, seed=11)
    b = reconcile_by_version(log, sink, sample_fraction=0.3, seed=11)
    assert a.keys_checked == 30
    assert a.diverged_keys == b.diverged_keys


def test_sampling_rounds_up_to_at_least_one_key():
    log = _log(_up(0, "a", 1, "v1"), _up(1, "b", 1, "w1"))
    sink = SinkState(values={"a": "v1", "b": "w1"}, committed_watermark=1)
    result = reconcile_by_version(log, sink, sample_fraction=0.01, seed=1)
    assert result.keys_checked == 1


def test_the_gap_detector_reports_an_unapplied_offset_below_the_watermark():
    log = _log(_up(0, "a", 1, "v1"), _up(1, "b", 1, "w1"), _up(2, "c", 1, "x1"))
    sink = SinkState(applied_offsets={0, 2}, committed_watermark=2)
    result = detect_offset_gaps(log, sink)
    assert result.diverged_keys == ("offset:1",)


def test_the_gap_detector_reports_nothing_on_an_empty_sink():
    log = _log(_up(0, "a", 1, "v1"))
    result = detect_offset_gaps(log, SinkState())
    assert result.diverged_count == 0


def test_false_alarms_are_offsets_below_the_watermark_with_no_source_record():
    # Offset 1 is a marker hole (no source event); offset 3 is a real unapplied record.
    log = _log(_up(0, "a", 1, "v1"), _up(2, "b", 1, "w1"), _up(3, "c", 1, "x1"))
    sink = SinkState(applied_offsets={0, 2}, committed_watermark=3)
    assert false_alarm_offsets(log, sink) == (1,)


def test_the_version_reconciler_raises_no_false_alarm_on_a_marker_hole():
    log = _log(_up(0, "a", 1, "v1"), _up(2, "b", 1, "w1"))
    sink = SinkState(
        values={"a": "v1", "b": "w1"},
        applied_offsets={0, 2},
        applied_lsn_by_key={"a": 1, "b": 1},
        committed_watermark=2,
    )
    assert reconcile_by_version(log, sink).clean


def test_false_alarm_offsets_is_empty_on_an_empty_sink():
    log = _log(_up(0, "a", 1, "v1"))
    assert false_alarm_offsets(log, SinkState()) == ()
