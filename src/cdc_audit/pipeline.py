"""Tie the stages together into one audit, so the CLI and the experiments agree.

Why this file exists: source, delivery, consumer and reconcile are deliberately
independent and ignorant of each other, which is right for testing them but wrong
for a caller who just wants an answer. This module is the single composition point.
If the CLI and an experiment ran the stages in slightly different orders, their
numbers would diverge and the receipts would be meaningless, so they both call here.
"""

from __future__ import annotations

from dataclasses import dataclass

from cdc_audit.config import Policy
from cdc_audit.consumer import consume
from cdc_audit.delivery import deliver
from cdc_audit.model import ReconcileResult, SinkState, SourceLog
from cdc_audit.reconcile import detect_offset_gaps, reconcile_by_version
from cdc_audit.source import generate_source


@dataclass(frozen=True, slots=True)
class AuditRun:
    source: SourceLog
    sink: SinkState
    result: ReconcileResult


def build_source(policy: Policy, *, txn_marker_every: int = 0) -> SourceLog:
    """Generate the changelog the policy describes, optionally with offset holes."""
    return generate_source(
        policy.seed,
        policy.keys,
        policy.events,
        txn_marker_every=txn_marker_every,
    )


def run_audit(policy: Policy, *, txn_marker_every: int = 0) -> AuditRun:
    """Run the full pipeline under a policy and return source, sink and verdict."""
    source = build_source(policy, txn_marker_every=txn_marker_every)
    delivered = deliver(source, reorder_window=policy.reorder_window, seed=policy.seed)
    sink = consume(delivered, skip_rule=policy.skip_rule, commit_interval=policy.commit_interval)
    if policy.method == "offset_gap":
        result = detect_offset_gaps(source, sink)
    else:
        result = reconcile_by_version(
            source,
            sink,
            sample_fraction=policy.sample_fraction,
            seed=policy.seed,
        )
    return AuditRun(source=source, sink=sink, result=result)
