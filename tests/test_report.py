"""Properties of the HTML report, including the badge-legibility guard that cost a prior build."""

from __future__ import annotations

import re

from cdc_audit.config import Policy, load_policy
from cdc_audit.pipeline import run_audit
from cdc_audit.report import _STYLE, render_report


def _clean_policy() -> Policy:
    return Policy(
        seed=20260219,
        keys=500,
        events=2000,
        reorder_window=8,
        commit_interval=16,
        skip_rule="offset",
        method="version",
        sample_fraction=1.0,
        max_diverged_keys=0,
    )


def test_a_violated_run_renders_the_fail_badge_and_wording():
    policy = load_policy("policy.toml")
    html = render_report(run_audit(policy), policy)
    assert "badgefail" in html
    assert "EXACTLY-ONCE VIOLATED" in html


def test_a_clean_run_renders_the_pass_badge_and_wording():
    policy = _clean_policy()
    html = render_report(run_audit(policy), policy)
    assert "badgepass" in html
    assert "RECONCILED" in html


def test_every_css_class_used_in_the_markup_has_a_rule():
    # The collision that shipped a green-on-green badge in a sibling project had no
    # rule guarding it. This asserts every class in the markup is actually styled.
    policy = load_policy("policy.toml")
    html = render_report(run_audit(policy), policy)
    used = set()
    for attr in re.findall(r'class="([^"]+)"', html):
        used.update(attr.split())
    for cls in used:
        assert f".{cls}" in _STYLE, f"class {cls!r} has no rule in the stylesheet"


def test_the_report_is_a_self_contained_document_with_no_external_assets():
    policy = load_policy("policy.toml")
    html = render_report(run_audit(policy), policy)
    assert html.startswith("<!DOCTYPE html>")
    assert "src=" not in html  # no external images
    assert "href=" not in html  # no external stylesheet
