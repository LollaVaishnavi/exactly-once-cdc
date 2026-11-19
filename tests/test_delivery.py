"""Properties of the delivery channel: deterministic, bounded displacement, lossless."""

from __future__ import annotations

import pytest

from cdc_audit.delivery import deliver, max_displacement
from cdc_audit.source import generate_source


def test_a_zero_window_delivers_events_in_source_order():
    log = generate_source(1, keys=20, events=80)
    assert deliver(log, reorder_window=0, seed=1) == log.events


def test_a_negative_window_is_refused():
    log = generate_source(1, keys=20, events=80)
    with pytest.raises(ValueError, match="reorder_window"):
        deliver(log, reorder_window=-1, seed=1)


def test_delivery_preserves_every_event_exactly_once():
    log = generate_source(1, keys=20, events=80)
    delivered = deliver(log, reorder_window=16, seed=1)
    assert sorted(e.offset for e in delivered) == sorted(e.offset for e in log.events)


def test_displacement_never_exceeds_the_window():
    log = generate_source(5, keys=50, events=300)
    for window in (4, 16, 40, 64):
        delivered = deliver(log, reorder_window=window, seed=5)
        assert max_displacement(log, delivered) <= window


def test_the_same_seed_delivers_the_same_order():
    log = generate_source(5, keys=50, events=300)
    a = deliver(log, reorder_window=32, seed=5)
    b = deliver(log, reorder_window=32, seed=5)
    assert a == b


def test_a_wider_window_reorders_more():
    log = generate_source(5, keys=50, events=300)
    narrow = max_displacement(log, deliver(log, reorder_window=4, seed=5))
    wide = max_displacement(log, deliver(log, reorder_window=48, seed=5))
    assert wide > narrow


def test_a_zero_window_has_zero_displacement():
    log = generate_source(5, keys=50, events=300)
    assert max_displacement(log, deliver(log, reorder_window=0, seed=5)) == 0
