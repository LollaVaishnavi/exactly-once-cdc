"""Render the audit as a self-contained HTML report with a legible verdict badge.

Why this file exists: the headline of an audit is a verdict, and a verdict that
renders invisibly is worse than none. An earlier sibling project shipped a badge
that came out green on green because a badge rule and a table-cell rule collided at
equal CSS specificity. So the stylesheet here gives the badge its own class with no
competing selector, and a test asserts that every class used in the markup has a
rule. The report is one self-contained file: no network, no external stylesheet, so
a reviewer opens it offline and sees exactly what CI screenshots.
"""

from __future__ import annotations

import html

from cdc_audit.config import Policy
from cdc_audit.pipeline import AuditRun
from cdc_audit.watermark import watermark_lag

_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #111;
       background: #fff; margin: 0; padding: 32px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 28px 0 8px; text-transform: uppercase;
     letter-spacing: 0.04em; color: #444; }
p.lede { color: #333; margin: 0 0 16px; max-width: 70ch; }
table.facts { border-collapse: collapse; width: 100%; max-width: 640px; }
table.facts td { border-top: 1px solid #e3e3e3; padding: 7px 10px; font-size: 14px; }
td.label { color: #555; }
td.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
span.verdictbadge { display: inline-block; padding: 8px 16px; border-radius: 6px;
       font-weight: 700; font-size: 15px; letter-spacing: 0.02em; }
span.badgefail { background: #b3261e; color: #ffffff; }
span.badgepass { background: #1b7a3d; color: #ffffff; }
span.watermarkzero { color: #b3261e; font-weight: 700; }
div.caption { color: #666; font-size: 12px; margin-top: 8px; max-width: 70ch; }
""".strip()


def _row(label: str, value: str, num_class: str = "num") -> str:
    return (
        f'<tr><td class="label">{html.escape(label)}</td>'
        f'<td class="{num_class}">{html.escape(value)}</td></tr>'
    )


def render_report(run: AuditRun, policy: Policy) -> str:
    """Return a complete HTML document summarising the audit and its verdict."""
    result = run.result
    lag = watermark_lag(run.source, run.sink)
    dropped = len(run.source.events) - len(run.sink.applied_offsets)

    if result.clean:
        badge = '<span class="verdictbadge badgepass">RECONCILED</span>'
        lede = (
            "The sink matches the source changelog under last-writer-wins. "
            "Exactly-once held for this run."
        )
    else:
        badge = '<span class="verdictbadge badgefail">EXACTLY-ONCE VIOLATED</span>'
        lede = (
            f"The consumer-lag watermark reports "
            f'<span class="watermarkzero">lag {lag}</span>, yet '
            f"{result.diverged_count} of {result.keys_total} keys hold a value the source "
            f"never agreed to. The dashboard cannot see this; the reconciler can."
        )

    facts = "".join(
        [
            _row("Reconcile method", result.method, "num"),
            _row("Source high offset", str(result.source_max_offset)),
            _row("Committed watermark", str(result.committed_watermark)),
            _row("Watermark lag (what the dashboard shows)", str(lag)),
            _row("Records silently dropped", str(dropped)),
            _row("Keys diverged (what reconciliation finds)", str(result.diverged_count)),
            _row("  of which missing", str(len(result.missing_keys))),
            _row("  of which stale or wrong", str(len(result.stale_keys))),
            _row("Keys checked / total", f"{result.keys_checked} / {result.keys_total}"),
        ]
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>cdc-audit report</title>
<style>{_STYLE}</style></head>
<body>
<h1>cdc-audit: exactly-once reconciliation</h1>
<p class="lede">{lede}</p>
<h2>Verdict</h2>
{badge}
<h2>Measurements</h2>
<table class="facts"><tbody>{facts}</tbody></table>
<div class="caption">Scenario: seed {policy.seed}, {policy.keys} keys, {policy.events} events,
reorder window {policy.reorder_window}, commit interval {policy.commit_interval},
skip rule {html.escape(policy.skip_rule)}. Every figure is produced by running the pipeline.</div>
</body></html>
"""
