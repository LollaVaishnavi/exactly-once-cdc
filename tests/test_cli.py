"""Properties of the CLI: the exit code is the contract between the tool and a monitor."""

from __future__ import annotations

import json

from cdc_audit.cli import EXIT_CANNOT_ANSWER, EXIT_CLEAN, EXIT_DIVERGED, main

CLEAN_POLICY = """
[source]
seed = 20260219
keys = 500
events = 2000
[delivery]
reorder_window = 8
commit_interval = 16
[consumer]
skip_rule = "offset"
[reconcile]
method = "version"
sample_fraction = 1.0
[verdict]
max_diverged_keys = 0
"""


def _write_policy(tmp_path, text):
    path = tmp_path / "policy.toml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_a_violated_scenario_exits_with_the_diverged_code(capsys):
    code = main(["--policy", "policy.toml"])
    assert code == EXIT_DIVERGED
    assert "EXACTLY-ONCE VIOLATED" in capsys.readouterr().out


def test_a_reconciled_scenario_exits_clean(tmp_path, capsys):
    code = main(["--policy", _write_policy(tmp_path, CLEAN_POLICY)])
    assert code == EXIT_CLEAN
    assert "RECONCILED" in capsys.readouterr().out


def test_a_missing_policy_exits_with_the_cannot_answer_code(capsys):
    code = main(["--policy", "does-not-exist.toml"])
    assert code == EXIT_CANNOT_ANSWER
    assert "cannot answer" in capsys.readouterr().err


def test_the_json_flag_prints_a_parseable_summary(capsys):
    code = main(["--policy", "policy.toml", "--json"])
    assert code == EXIT_DIVERGED
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "diverged"
    assert payload["watermark_lag"] == 0
    assert payload["diverged_keys"] == 40


def test_the_report_flag_writes_a_self_contained_html_file(tmp_path, capsys):
    report = tmp_path / "report.html"
    code = main(["--policy", "policy.toml", "--report", str(report)])
    assert code == EXIT_DIVERGED
    text = report.read_text(encoding="utf-8")
    assert "EXACTLY-ONCE VIOLATED" in text
    assert "report written" in capsys.readouterr().out


def test_the_txn_markers_flag_runs_the_pipeline_on_a_sparse_log(capsys):
    code = main(["--policy", "policy.toml", "--txn-markers", "50", "--json"])
    assert code == EXIT_DIVERGED
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_max_offset"] > 1999  # holes widened the offset span
