"""Load and validate policy.toml, so no threshold or path is hardcoded in src/.

Why this file exists: the audit has to be rerunnable under a different policy by a
reviewer who never opens the source. Centralising the parse here means every knob
is validated once, with a message that names the offending field, rather than
failing deep inside the reconciler with a KeyError.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from cdc_audit.model import CdcAuditError

SKIP_RULES = ("offset", "version")
RECONCILE_METHODS = ("version", "offset_gap")


@dataclass(frozen=True, slots=True)
class Policy:
    seed: int
    keys: int
    events: int
    reorder_window: int
    commit_interval: int
    skip_rule: str
    method: str
    sample_fraction: float
    max_diverged_keys: int

    def __post_init__(self) -> None:
        if self.keys < 1:
            raise CdcAuditError("source.keys must be at least 1")
        if self.events < self.keys:
            raise CdcAuditError("source.events must be at least source.keys (one change per key)")
        if self.reorder_window < 0:
            raise CdcAuditError("delivery.reorder_window must not be negative")
        if self.commit_interval < 1:
            raise CdcAuditError("delivery.commit_interval must be at least 1")
        if self.skip_rule not in SKIP_RULES:
            raise CdcAuditError(f"consumer.skip_rule must be one of {SKIP_RULES}")
        if self.method not in RECONCILE_METHODS:
            raise CdcAuditError(f"reconcile.method must be one of {RECONCILE_METHODS}")
        if not 0.0 < self.sample_fraction <= 1.0:
            raise CdcAuditError("reconcile.sample_fraction must be in (0, 1]")
        if self.max_diverged_keys < 0:
            raise CdcAuditError("verdict.max_diverged_keys must not be negative")


def _require(table: dict, section: str, key: str):
    try:
        return table[section][key]
    except KeyError as exc:
        raise CdcAuditError(f"policy is missing [{section}].{key}") from exc


def load_policy(path: str | Path) -> Policy:
    """Read policy.toml into a validated Policy, or raise CdcAuditError with context."""
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CdcAuditError(f"policy file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CdcAuditError(f"policy file is not valid TOML: {exc}") from exc

    return Policy(
        seed=_require(raw, "source", "seed"),
        keys=_require(raw, "source", "keys"),
        events=_require(raw, "source", "events"),
        reorder_window=_require(raw, "delivery", "reorder_window"),
        commit_interval=_require(raw, "delivery", "commit_interval"),
        skip_rule=_require(raw, "consumer", "skip_rule"),
        method=_require(raw, "reconcile", "method"),
        sample_fraction=_require(raw, "reconcile", "sample_fraction"),
        max_diverged_keys=_require(raw, "verdict", "max_diverged_keys"),
    )
