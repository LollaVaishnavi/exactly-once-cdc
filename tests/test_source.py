"""Properties of the source generator: deterministic, dense per key, optionally sparse offsets."""

from __future__ import annotations

import pytest

from cdc_audit.model import DELETE
from cdc_audit.source import generate_source


def test_the_generator_produces_the_requested_number_of_events():
    log = generate_source(1, keys=20, events=80)
    assert len(log.events) == 80


def test_every_key_appears_at_least_once():
    log = generate_source(1, keys=20, events=80)
    assert log.keys == frozenset(f"k{i:04d}" for i in range(20))


def test_requesting_fewer_events_than_keys_is_refused():
    with pytest.raises(ValueError, match="at least keys"):
        generate_source(1, keys=20, events=5)


def test_the_same_seed_produces_byte_identical_logs():
    a = generate_source(7, keys=30, events=120)
    b = generate_source(7, keys=30, events=120)
    assert a.events == b.events


def test_a_different_seed_produces_a_different_log():
    a = generate_source(7, keys=30, events=120)
    b = generate_source(8, keys=30, events=120)
    assert a.events != b.events


def test_each_keys_versions_increase_by_exactly_one():
    log = generate_source(3, keys=15, events=90)
    seen: dict[str, int] = {}
    for event in log.events:
        expected = seen.get(event.key, 0) + 1
        assert event.lsn == expected, f"{event.key} jumped to {event.lsn}"
        seen[event.key] = event.lsn


def test_offsets_are_contiguous_when_no_markers_are_inserted():
    log = generate_source(3, keys=15, events=90)
    offsets = [e.offset for e in log.events]
    assert offsets == list(range(len(offsets)))


def test_transaction_markers_leave_holes_in_the_offset_space():
    log = generate_source(3, keys=15, events=90, txn_marker_every=10, txn_marker_width=2)
    offsets = [e.offset for e in log.events]
    # With holes, the offset span exceeds the event count.
    assert log.max_offset + 1 > len(offsets)


def test_a_wider_marker_leaves_a_larger_span():
    narrow = generate_source(3, keys=15, events=90, txn_marker_every=10, txn_marker_width=1)
    wide = generate_source(3, keys=15, events=90, txn_marker_every=10, txn_marker_width=5)
    assert wide.max_offset > narrow.max_offset


def test_the_first_change_for_a_key_is_never_a_delete():
    log = generate_source(99, keys=40, events=400, delete_fraction=0.9)
    first_seen: set[str] = set()
    for event in log.events:
        if event.key not in first_seen:
            assert event.op != DELETE
            first_seen.add(event.key)


def test_deletes_appear_when_the_delete_fraction_is_high():
    log = generate_source(99, keys=40, events=400, delete_fraction=0.9)
    assert any(e.op == DELETE for e in log.events)


def test_no_deletes_appear_when_the_delete_fraction_is_zero():
    log = generate_source(99, keys=40, events=400, delete_fraction=0.0)
    assert all(e.op != DELETE for e in log.events)
