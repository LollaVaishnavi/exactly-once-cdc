"""Properties of the consumer: the buffer absorbs reorder; the offset rule drops, version keeps."""

from __future__ import annotations

import pytest

from cdc_audit.consumer import consume
from cdc_audit.delivery import deliver
from cdc_audit.model import DELETE, UPSERT, ChangeEvent
from cdc_audit.reconcile import reconcile_by_version
from cdc_audit.source import generate_source


def _run(window, buffer, skip_rule, seed=20260219, keys=500, events=2000):
    log = generate_source(seed, keys, events)
    delivered = deliver(log, reorder_window=window, seed=seed)
    sink = consume(delivered, skip_rule=skip_rule, commit_interval=buffer)
    return log, sink


def test_an_unknown_skip_rule_is_refused():
    with pytest.raises(ValueError, match="skip_rule"):
        consume((), skip_rule="magic", commit_interval=4)


def test_a_zero_commit_interval_is_refused():
    with pytest.raises(ValueError, match="commit_interval"):
        consume((), skip_rule="offset", commit_interval=0)


def test_a_reorder_within_the_buffer_loses_nothing_under_the_offset_rule():
    log, sink = _run(window=16, buffer=16, skip_rule="offset")
    result = reconcile_by_version(log, sink)
    assert result.diverged_count == 0


def test_a_reorder_beyond_the_buffer_loses_rows_under_the_offset_rule():
    log, sink = _run(window=40, buffer=16, skip_rule="offset")
    result = reconcile_by_version(log, sink)
    assert result.diverged_count > 0


def test_a_wider_window_loses_at_least_as_many_rows():
    log_a, sink_a = _run(window=24, buffer=16, skip_rule="offset")
    log_b, sink_b = _run(window=48, buffer=16, skip_rule="offset")
    few = reconcile_by_version(log_a, sink_a).diverged_count
    many = reconcile_by_version(log_b, sink_b).diverged_count
    assert many >= few


def test_the_version_rule_loses_nothing_even_past_the_buffer():
    log, sink = _run(window=64, buffer=16, skip_rule="version")
    result = reconcile_by_version(log, sink)
    assert result.diverged_count == 0


def test_the_offset_rule_leaves_the_watermark_fully_advanced():
    log, sink = _run(window=40, buffer=16, skip_rule="offset")
    assert sink.committed_watermark == log.max_offset


def test_an_in_order_stream_applies_every_record():
    log = generate_source(1, keys=30, events=120)
    sink = consume(log.events, skip_rule="offset", commit_interval=8)
    assert len(sink.applied_offsets) == len(log.events)


def test_a_delete_removes_the_key_from_the_sink():
    events = (
        ChangeEvent(offset=0, key="k", lsn=1, op=UPSERT, value="v1"),
        ChangeEvent(offset=1, key="k", lsn=2, op=DELETE, value=None),
    )
    sink = consume(events, skip_rule="offset", commit_interval=4)
    assert "k" not in sink.values


def test_an_upsert_sets_the_latest_value_in_the_sink():
    events = (
        ChangeEvent(offset=0, key="k", lsn=1, op=UPSERT, value="v1"),
        ChangeEvent(offset=1, key="k", lsn=2, op=UPSERT, value="v2"),
    )
    sink = consume(events, skip_rule="version", commit_interval=4)
    assert sink.values["k"] == "v2"


def test_the_version_rule_records_the_highest_applied_lsn_per_key():
    events = (
        ChangeEvent(offset=0, key="k", lsn=1, op=UPSERT, value="v1"),
        ChangeEvent(offset=1, key="k", lsn=2, op=UPSERT, value="v2"),
    )
    sink = consume(events, skip_rule="version", commit_interval=4)
    assert sink.applied_lsn_by_key["k"] == 2
