"""Command-line entry point. Exit codes carry the verdict, so CI can branch on them.

Why this file exists: a reviewer, and a pipeline, need to tell three outcomes apart
without parsing prose. The exit code is the contract:

  0  exactly-once held: the sink reconciles against the source.
  1  divergence found: the audit ran and the answer is no. This is a successful run
     of the tool, not an error, which is why it is distinct from code 2.
  2  the tool could not answer: a bad policy, an unreadable file, an inconsistent
     log. Nothing is asserted about exactly-once in this case.

Keeping 1 and 2 separate is the point. A monitor that treats "the audit crashed" as
"the data is fine" is the same class of mistake this whole project is about.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cdc_audit.config import load_policy
from cdc_audit.model import CdcAuditError
from cdc_audit.pipeline import run_audit
from cdc_audit.report import render_report
from cdc_audit.watermark import watermark_lag

EXIT_CLEAN = 0
EXIT_DIVERGED = 1
EXIT_CANNOT_ANSWER = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdc-audit",
        description="Audit a CDC pipeline for exactly-once violations a lag dashboard cannot see.",
    )
    parser.add_argument(
        "--policy",
        default="policy.toml",
        help="path to the policy file (default: policy.toml)",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="also write a self-contained HTML report to PATH",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the summary as JSON instead of text",
    )
    parser.add_argument(
        "--txn-markers",
        type=int,
        default=0,
        metavar="EVERY",
        help="insert a transaction-marker offset hole every EVERY events (0 = none)",
    )
    return parser


def _summary(run, lag: int) -> dict:
    result = run.result
    return {
        "method": result.method,
        "source_max_offset": result.source_max_offset,
        "committed_watermark": result.committed_watermark,
        "watermark_lag": lag,
        "records_dropped": len(run.source.events) - len(run.sink.applied_offsets),
        "diverged_keys": result.diverged_count,
        "missing_keys": len(result.missing_keys),
        "stale_keys": len(result.stale_keys),
        "keys_checked": result.keys_checked,
        "keys_total": result.keys_total,
        "verdict": "clean" if result.clean else "diverged",
    }


def main(argv: list[str] | None = None) -> int:
    """Run the audit and return an exit code. Importable for tests; never calls sys.exit."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.policy)
        run = run_audit(policy, txn_marker_every=args.txn_markers)
        lag = watermark_lag(run.source, run.sink)
        summary = _summary(run, lag)

        if args.report:
            Path(args.report).write_text(render_report(run, policy), encoding="utf-8")

        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            _print_text(summary, args.report)
    except CdcAuditError as exc:
        print(f"cdc-audit: cannot answer: {exc}", file=sys.stderr)
        return EXIT_CANNOT_ANSWER

    return EXIT_CLEAN if run.result.clean else EXIT_DIVERGED


def _print_text(summary: dict, report_path: str | None) -> None:
    verdict = "RECONCILED" if summary["verdict"] == "clean" else "EXACTLY-ONCE VIOLATED"
    print(f"method              : {summary['method']}")
    print(f"watermark lag       : {summary['watermark_lag']}  (what a lag dashboard shows)")
    print(f"records dropped     : {summary['records_dropped']}")
    print(f"keys diverged       : {summary['diverged_keys']} of {summary['keys_total']}")
    print(f"  missing           : {summary['missing_keys']}")
    print(f"  stale or wrong    : {summary['stale_keys']}")
    print(f"verdict             : {verdict}")
    if report_path:
        print(f"report written      : {report_path}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
