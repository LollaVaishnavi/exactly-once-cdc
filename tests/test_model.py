"""Properties of the data model: the vocabulary every other module relies on."""

from __future__ import annotations

import pytest

from cdc_audit.model import (
    DELETE,
    UPSERT,
    CdcAuditError,
    ChangeEvent,
    ReconcileResult,
    SinkState,
    SourceLog,
)


def _upsert(offset: int, key: str, lsn: int) -> ChangeEvent:
    return ChangeEvent(offset=offset, key=key, lsn=lsn, op=UPSERT, value=f"v{lsn}")


def test_an_upsert_event_keeps_its_value():
    event = _upsert(0, "k", 1)
    assert event.value == "v1"


def test_a_delete_event_carries_a_null_value():
    event = ChangeEvent(offset=0, key="k", lsn=2, op=DELETE, value=None)
    assert event.value is None


def test_an_event_with_an_unknown_operation_is_rejected():
    with pytest.raises(CdcAuditError, match="unknown operation"):
        ChangeEvent(offset=0, key="k", lsn=1, op="merge", value="v")


def test_a_delete_event_carrying_a_value_is_rejected():
    with pytest.raises(CdcAuditError, match="tombstone"):
        ChangeEvent(offset=0, key="k", lsn=1, op=DELETE, value="x")


def test_an_upsert_event_with_a_null_value_is_rejected():
    with pytest.raises(CdcAuditError, match="non-null"):
        ChangeEvent(offset=0, key="k", lsn=1, op=UPSERT, value=None)


def test_an_empty_source_log_is_rejected():
    with pytest.raises(CdcAuditError, match="at least one event"):
        SourceLog(events=())


def test_source_events_out_of_offset_order_are_rejected():
    events = (_upsert(5, "a", 1), _upsert(2, "b", 1))
    with pytest.raises(CdcAuditError, match="non-decreasing offset"):
        SourceLog(events=events)


def test_duplicate_source_offsets_are_rejected():
    events = (_upsert(1, "a", 1), _upsert(1, "b", 1))
    with pytest.raises(CdcAuditError, match="unique"):
        SourceLog(events=events)


def test_source_max_offset_is_the_last_events_offset():
    log = SourceLog(events=(_upsert(0, "a", 1), _upsert(7, "b", 1)))
    assert log.max_offset == 7


def test_source_keys_is_the_set_of_all_keys_seen():
    log = SourceLog(events=(_upsert(0, "a", 1), _upsert(1, "b", 1), _upsert(2, "a", 2)))
    assert log.keys == frozenset({"a", "b"})


def test_latest_by_key_picks_the_highest_lsn_per_key():
    log = SourceLog(events=(_upsert(0, "a", 1), _upsert(1, "a", 2), _upsert(2, "b", 1)))
    latest = log.latest_by_key()
    assert latest["a"].lsn == 2
    assert latest["b"].lsn == 1


def test_latest_by_key_keeps_a_delete_as_the_final_state():
    events = (_upsert(0, "a", 1), ChangeEvent(offset=1, key="a", lsn=2, op=DELETE, value=None))
    log = SourceLog(events=events)
    assert log.latest_by_key()["a"].op == DELETE


def test_a_fresh_sink_is_empty_with_a_negative_watermark():
    sink = SinkState()
    assert sink.values == {}
    assert sink.applied_offsets == set()
    assert sink.committed_watermark == -1


def test_a_reconcile_result_with_no_diverged_keys_is_clean():
    result = ReconcileResult(
        source_max_offset=9,
        committed_watermark=9,
        watermark_lag=0,
        diverged_keys=(),
        missing_keys=(),
        stale_keys=(),
        method="version",
        keys_checked=3,
        keys_total=3,
    )
    assert result.clean
    assert result.diverged_count == 0


def test_a_reconcile_result_with_diverged_keys_is_not_clean():
    result = ReconcileResult(
        source_max_offset=9,
        committed_watermark=9,
        watermark_lag=0,
        diverged_keys=("a", "b"),
        missing_keys=("a",),
        stale_keys=("b",),
        method="version",
        keys_checked=3,
        keys_total=3,
    )
    assert not result.clean
    assert result.diverged_count == 2
