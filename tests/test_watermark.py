"""Properties of the watermark view: it is one subtraction and sees nothing else."""

from __future__ import annotations

from cdc_audit.config import load_policy
from cdc_audit.model import SinkState
from cdc_audit.pipeline import run_audit
from cdc_audit.source import generate_source
from cdc_audit.watermark import watermark_lag


def test_lag_is_the_source_high_offset_minus_the_watermark():
    log = generate_source(1, keys=10, events=40)
    sink = SinkState(committed_watermark=30)
    assert watermark_lag(log, sink) == log.max_offset - 30


def test_a_fully_committed_watermark_reports_zero_lag():
    log = generate_source(1, keys=10, events=40)
    sink = SinkState(committed_watermark=log.max_offset)
    assert watermark_lag(log, sink) == 0


def test_the_shipped_scenario_reports_zero_lag_while_rows_are_wrong():
    policy = load_policy("policy.toml")
    run = run_audit(policy)
    assert watermark_lag(run.source, run.sink) == 0
    assert run.result.diverged_count > 0
