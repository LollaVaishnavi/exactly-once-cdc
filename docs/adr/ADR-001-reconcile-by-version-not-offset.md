# ADR-001: Reconcile by per-key version, not by offset contiguity

Status: accepted

## Context

The tool has to decide whether a sink is complete. The obvious, cheap signal is the offset
sequence: the consumer applied a set of offsets, so any offset below the committed watermark that
is not in that set looks like a lost record. It needs no changelog and almost no memory.

The first implementation did exactly that. It failed the moment it met a transactional topic. A
Kafka transaction commit marker consumes an offset without carrying a row, and log compaction
removes offsets whose key was later superseded. Both are legitimate, and both leave holes in the
offset sequence. The offset-gap detector reported one lost row per marker on a topic that had lost
nothing: on the shipped transactional fixture it raised 99 false alarms.

That is not a tuning problem. An offset-gap detector has no way, even in principle, to tell a hole
left by a marker from a hole left by a dropped record, because it never sees the records. The
information needed to tell them apart is in the changelog, which the detector deliberately does not
read.

## Decision

Reconcile the sink against the source changelog by **per-key version**. For each key, compare the
value materialised in the sink against the value of the newest change the source holds for that key,
chosen by its per-key logical version (lsn). A key is divergent when those differ. Offsets are not
consulted in the verdict at all.

## Alternatives considered

- **Offset-gap detection.** Rejected as the primary verdict because it cannot distinguish a marker
  hole from a lost record. It is kept in the code as `detect_offset_gaps`, used only to quantify the
  false-alarm cost in experiment C, which is more valuable than deleting it.
- **A hybrid that subtracts known marker offsets from the gap set.** Rejected: it needs a list of
  marker offsets, which is a changelog by another name, so it pays the memory cost of reconciliation
  while keeping the fragility of offset counting.

## Consequences

- The reconciler needs the source changelog and O(keys) memory for the per-key truth. ADR-005
  covers the memory-bounded variant and what it gives up.
- False alarms on a transactional or compacted topic drop to zero, structurally, because an offset
  hole can no longer influence the verdict. `tests/test_war_story.py` pins this so the regression
  cannot return unnoticed.
- The tool now depends on the changelog being trustworthy. ADR-004 states that boundary.
