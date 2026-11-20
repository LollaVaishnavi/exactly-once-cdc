"""Shared plumbing for the experiments, so each one is a question and an answer.

Why this file exists: the experiments must agree with the CLI and with each other on
exactly how a run is built, or their numbers drift and the receipts become fiction.
Every experiment therefore builds its runs through here, writes its result as sorted
JSON to docs/experiments/, and prints a small table. Nothing is timed, so every
published figure is a count or a ratio and is identical on any machine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cdc_audit.consumer import consume  # noqa: E402
from cdc_audit.delivery import deliver  # noqa: E402
from cdc_audit.model import ChangeEvent, SinkState, SourceLog  # noqa: E402
from cdc_audit.reconcile import reconcile_by_version  # noqa: E402
from cdc_audit.source import generate_source  # noqa: E402
from cdc_audit.watermark import watermark_lag  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "experiments"

# The shipped scenario, kept in one place so experiments and the policy file match.
SEED = 20260219
KEYS = 500
EVENTS = 2000
WINDOW = 40
BUFFER = 16


def shipped_source(*, txn_marker_every: int = 0) -> SourceLog:
    return generate_source(SEED, KEYS, EVENTS, txn_marker_every=txn_marker_every)


def run(
    source: SourceLog,
    *,
    window: int,
    buffer: int,
    skip_rule: str,
    delivered: tuple[ChangeEvent, ...] | None = None,
) -> SinkState:
    """Deliver and consume a source, optionally with a pre-built delivered stream."""
    if delivered is None:
        delivered = deliver(source, reorder_window=window, seed=SEED)
    return consume(delivered, skip_rule=skip_rule, commit_interval=buffer)


def measure(source: SourceLog, sink: SinkState) -> dict:
    """The standard bundle of figures every experiment reports for a run."""
    result = reconcile_by_version(source, sink)
    return {
        "watermark_lag": watermark_lag(source, sink),
        "records_dropped": len(source.events) - len(sink.applied_offsets),
        "diverged_keys": result.diverged_count,
        "missing_keys": len(result.missing_keys),
        "stale_keys": len(result.stale_keys),
        "keys_total": result.keys_total,
    }


def write(name: str, payload: dict) -> Path:
    """Write an experiment result as stable, sorted JSON and return its path."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_table(title: str, rows: list[tuple[str, str]]) -> None:
    print(title)
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"  {label.ljust(width)} : {value}")
