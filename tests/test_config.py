"""Properties of policy loading: every knob validated once, with a named field on error."""

from __future__ import annotations

import pytest

from cdc_audit.config import Policy, load_policy
from cdc_audit.model import CdcAuditError

VALID = """
[source]
seed = 1
keys = 10
events = 40
[delivery]
reorder_window = 8
commit_interval = 4
[consumer]
skip_rule = "offset"
[reconcile]
method = "version"
sample_fraction = 1.0
[verdict]
max_diverged_keys = 0
"""


def _write(tmp_path, text):
    path = tmp_path / "policy.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_policy_file_loads():
    policy = load_policy("policy.toml")
    assert policy.skip_rule in ("offset", "version")


def test_a_valid_policy_round_trips_every_field(tmp_path):
    policy = load_policy(_write(tmp_path, VALID))
    assert policy == Policy(
        seed=1,
        keys=10,
        events=40,
        reorder_window=8,
        commit_interval=4,
        skip_rule="offset",
        method="version",
        sample_fraction=1.0,
        max_diverged_keys=0,
    )


def test_a_missing_file_is_reported_as_cannot_answer(tmp_path):
    with pytest.raises(CdcAuditError, match="not found"):
        load_policy(tmp_path / "absent.toml")


def test_malformed_toml_is_reported_with_context(tmp_path):
    with pytest.raises(CdcAuditError, match="not valid TOML"):
        load_policy(_write(tmp_path, "this is = = not toml"))


def test_a_missing_section_key_names_the_field(tmp_path):
    text = VALID.replace("seed = 1\n", "")
    with pytest.raises(CdcAuditError, match=r"\[source\].seed"):
        load_policy(_write(tmp_path, text))


def test_zero_keys_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="source.keys"):
        load_policy(_write(tmp_path, VALID.replace("keys = 10", "keys = 0")))


def test_fewer_events_than_keys_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="at least source.keys"):
        load_policy(_write(tmp_path, VALID.replace("events = 40", "events = 5")))


def test_a_negative_reorder_window_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="reorder_window"):
        load_policy(_write(tmp_path, VALID.replace("reorder_window = 8", "reorder_window = -1")))


def test_a_zero_commit_interval_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="commit_interval"):
        load_policy(_write(tmp_path, VALID.replace("commit_interval = 4", "commit_interval = 0")))


def test_an_unknown_skip_rule_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="skip_rule"):
        load_policy(_write(tmp_path, VALID.replace('skip_rule = "offset"', 'skip_rule = "magic"')))


def test_an_unknown_reconcile_method_is_rejected(tmp_path):
    with pytest.raises(CdcAuditError, match="method"):
        load_policy(_write(tmp_path, VALID.replace('method = "version"', 'method = "guess"')))


def test_a_sample_fraction_above_one_is_rejected(tmp_path):
    text = VALID.replace("sample_fraction = 1.0", "sample_fraction = 2.0")
    with pytest.raises(CdcAuditError, match="sample_fraction"):
        load_policy(_write(tmp_path, text))


def test_a_zero_sample_fraction_is_rejected(tmp_path):
    text = VALID.replace("sample_fraction = 1.0", "sample_fraction = 0.0")
    with pytest.raises(CdcAuditError, match="sample_fraction"):
        load_policy(_write(tmp_path, text))


def test_a_negative_max_diverged_keys_is_rejected(tmp_path):
    text = VALID.replace("max_diverged_keys = 0", "max_diverged_keys = -1")
    with pytest.raises(CdcAuditError, match="max_diverged_keys"):
        load_policy(_write(tmp_path, text))
