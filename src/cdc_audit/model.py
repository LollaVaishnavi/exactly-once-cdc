"""The data model, kept in one file so every other module agrees on the vocabulary.

Why this file exists: the whole argument of the project turns on three distinct
coordinates that production dashboards routinely conflate.

  offset   the position of a record in the partition log. Monotonic at the
           source, but NOT dense: transaction control records and compaction
           both remove offsets that never carried a usable row. The watermark is
           an offset, and that is the root of its blind spot.
  lsn      a per-key logical version. It says which write is newer for a given
           key, independent of where the record landed in the log. Last-writer
           -wins correctness is defined against the lsn, not the offset.
  key      the primary key whose latest value the sink is supposed to hold.

Separating these three into named fields, rather than reusing the offset as if it
were a version, is what lets the reconciler catch loss the watermark cannot. The
error class is defined here too so callers import failures from the same place as
the types that raise them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Operations a change event can carry. A delete is modelled as a tombstone value
# so the sink can distinguish "key absent because deleted" from "key never seen".
UPSERT = "upsert"
DELETE = "delete"
OPERATIONS = (UPSERT, DELETE)


class CdcAuditError(Exception):
    """Raised when the tool cannot answer, as opposed to answering 'not exactly-once'.

    The CLI maps this to exit code 2. It is deliberately distinct from a clean
    'divergence found' result, because a reviewer must be able to tell 'the audit
    ran and the answer is no' from 'the audit could not run'.
    """


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """One row-level change in the log.

    offset is the log position (monotonic, possibly sparse). lsn is the per-key
    version (monotonic per key, dense per key by construction of the source).
    """

    offset: int
    key: str
    lsn: int
    op: str
    value: str | None

    def __post_init__(self) -> None:
        if self.op not in OPERATIONS:
            raise CdcAuditError(f"unknown operation {self.op!r}, expected one of {OPERATIONS}")
        if self.op == DELETE and self.value is not None:
            raise CdcAuditError("a delete event must carry a null value (tombstone)")
        if self.op == UPSERT and self.value is None:
            raise CdcAuditError("an upsert event must carry a non-null value")


@dataclass(frozen=True, slots=True)
class SourceLog:
    """The authoritative changelog: the ground truth the sink is audited against.

    events are in source offset order. The source guarantees that for each key the
    lsn increases by exactly one per change, so a gap in a key's lsn sequence in
    the sink is unambiguous evidence of loss, not of a sparse log.
    """

    events: tuple[ChangeEvent, ...]

    def __post_init__(self) -> None:
        if not self.events:
            raise CdcAuditError("a source log must contain at least one event")
        offsets = [e.offset for e in self.events]
        if offsets != sorted(offsets):
            raise CdcAuditError("source events must be in non-decreasing offset order")
        if len(set(offsets)) != len(offsets):
            raise CdcAuditError("source offsets must be unique")

    @property
    def max_offset(self) -> int:
        return self.events[-1].offset

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(e.key for e in self.events)

    def latest_by_key(self) -> dict[str, ChangeEvent]:
        """The last-writer-wins truth: the newest event per key, chosen by lsn.

        This is the oracle the sink is compared against. A key whose newest event
        is a delete is expected to be absent from the sink.
        """
        latest: dict[str, ChangeEvent] = {}
        for event in self.events:
            current = latest.get(event.key)
            if current is None or event.lsn > current.lsn:
                latest[event.key] = event
        return latest


@dataclass(slots=True)
class SinkState:
    """What the consumer actually materialised, plus the watermark it committed.

    values holds the live rows (deletes remove the key). applied_offsets is the
    exact set of source offsets the consumer applied, which the reconciler needs
    to distinguish an offset that was skipped from one that was never delivered.
    applied_lsn_by_key records, per key, the newest lsn the sink absorbed, which
    is what version reconciliation compares.
    """

    values: dict[str, str] = field(default_factory=dict)
    applied_offsets: set[int] = field(default_factory=set)
    applied_lsn_by_key: dict[str, int] = field(default_factory=dict)
    committed_watermark: int = -1


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    """The verdict: which keys diverged and why, with the watermark's own view.

    watermark_lag is what a lag dashboard would show. diverged_keys is what the
    reconciler found. The gap between the two is the entire point of the project,
    so both travel together in one result rather than being reported separately.
    """

    source_max_offset: int
    committed_watermark: int
    watermark_lag: int
    diverged_keys: tuple[str, ...]
    missing_keys: tuple[str, ...]
    stale_keys: tuple[str, ...]
    method: str
    keys_checked: int
    keys_total: int

    @property
    def diverged_count(self) -> int:
        return len(self.diverged_keys)

    @property
    def clean(self) -> bool:
        return self.diverged_count == 0
