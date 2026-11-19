"""Generate a deterministic, seeded source changelog: the ground truth for an audit.

Why this file exists: the audit needs a changelog whose completeness is known with
certainty, so that any divergence found in the sink is attributable to the pipeline
and never to an ambiguous input. A seeded generator gives exactly that, and lets a
reviewer reproduce every number with one command and no network.

Two properties are built in on purpose.

  Per-key dense lsn. Each key's version increases by exactly one per change, so a
  missing version in the sink is unambiguous evidence of loss, not of a naturally
  sparse history.

  Optionally sparse offsets. Real transactional topics leave holes in the offset
  space because transaction commit markers consume an offset without carrying a
  row. The generator can insert those holes so the offset-gap detector can be shown
  raising false alarms on a log that lost nothing.
"""

from __future__ import annotations

import hashlib
import random

from cdc_audit.model import DELETE, UPSERT, ChangeEvent, SourceLog


def _value_for(key: str, lsn: int) -> str:
    """A stable, distinct value per (key, lsn), so a wrong value is detectable."""
    return hashlib.sha1(f"{key}:{lsn}".encode()).hexdigest()[:8]


def generate_source(
    seed: int,
    keys: int,
    events: int,
    *,
    delete_fraction: float = 0.05,
    txn_marker_every: int = 0,
    txn_marker_width: int = 1,
) -> SourceLog:
    """Build a SourceLog of `events` changes across `keys` keys, deterministically.

    Every key gets at least one creating upsert, so `events` must be at least
    `keys`. A small fraction of later changes are deletes. When txn_marker_every is
    positive, the offset counter jumps by txn_marker_width extra positions every
    txn_marker_every events, leaving legitimate holes in the offset space.
    """
    if events < keys:
        raise ValueError("events must be at least keys")
    rng = random.Random(seed)

    key_names = [f"k{i:04d}" for i in range(keys)]
    next_lsn = dict.fromkeys(key_names, 0)

    # First, one creating upsert per key so every key exists. Then distribute the
    # remaining changes over randomly chosen keys.
    order: list[str] = list(key_names)
    for _ in range(events - keys):
        order.append(rng.choice(key_names))
    rng.shuffle(order)

    built: list[ChangeEvent] = []
    offset = 0
    for i, key in enumerate(order):
        next_lsn[key] += 1
        lsn = next_lsn[key]
        # A key's very first change must create it, so deletes only after lsn 1.
        if lsn > 1 and rng.random() < delete_fraction:
            op, value = DELETE, None
        else:
            op, value = UPSERT, _value_for(key, lsn)
        built.append(ChangeEvent(offset=offset, key=key, lsn=lsn, op=op, value=value))
        offset += 1
        if txn_marker_every and (i + 1) % txn_marker_every == 0:
            # A transaction commit marker consumes offsets without carrying a row.
            offset += txn_marker_width

    return SourceLog(events=tuple(built))
