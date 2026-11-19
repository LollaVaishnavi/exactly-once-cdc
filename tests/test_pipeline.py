"""Properties of the composed pipeline, and the frozen numbers of the shipped scenario."""

from __future__ import annotations

from cdc_audit.config import Policy, load_policy
from cdc_audit.pipeline import build_source, run_audit


def _policy(**overrides) -> Policy:
    base = {
        "seed": 20260219,
        "keys": 500,
        "events": 2000,
        "reorder_window": 40,
        "commit_interval": 16,
        "skip_rule": "offset",
        "method": "version",
        "sample_fraction": 1.0,
        "max_diverged_keys": 0,
    }
    base.update(overrides)
    return Policy(**base)


def test_the_shipped_scenario_has_the_frozen_headline_numbers():
    run = run_audit(load_policy("policy.toml"))
    dropped = len(run.source.events) - len(run.sink.applied_offsets)
    assert run.result.watermark_lag == 0
    assert run.result.diverged_count == 40
    assert len(run.result.missing_keys) == 4
    assert len(run.result.stale_keys) == 36
    assert dropped == 153
    assert run.result.source_max_offset == 1999
    assert run.result.committed_watermark == 1999


def test_the_shipped_scenario_is_reproducible_run_to_run():
    a = run_audit(load_policy("policy.toml"))
    b = run_audit(load_policy("policy.toml"))
    assert a.result.diverged_keys == b.result.diverged_keys
    assert a.sink.values == b.sink.values


def test_the_offset_gap_method_is_dispatched_by_policy():
    run = run_audit(_policy(method="offset_gap"))
    assert run.result.method == "offset_gap"


def test_the_version_method_is_dispatched_by_policy():
    run = run_audit(_policy(method="version"))
    assert run.result.method == "version"


def test_a_window_within_the_buffer_reconciles_clean():
    run = run_audit(_policy(reorder_window=8, commit_interval=16))
    assert run.result.clean


def test_transaction_markers_make_the_source_offsets_sparse():
    dense = build_source(_policy())
    sparse = build_source(_policy(), txn_marker_every=50)
    assert sparse.max_offset > dense.max_offset
