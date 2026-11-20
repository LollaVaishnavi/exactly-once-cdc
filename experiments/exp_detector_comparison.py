"""Experiment C: what does the cheap offset-gap detector cost on a transactional topic?

Question the README asks: the offset-gap detector needs no changelog and O(1) extra
state, so why not use it? Because a transaction commit marker consumes an offset
without carrying a row, so on a topic that lost nothing the offset-gap detector still
raises one alarm per marker, while the version reconciler raises none. This is the
two-column trade-off: cheap and wrong against costly and correct.
"""

from __future__ import annotations

import harness
from cdc_audit.reconcile import detect_offset_gaps, false_alarm_offsets, reconcile_by_version

MARKER_EVERY = 20
MARKER_WIDTH = 2


def run() -> dict:
    # A transactional topic that lost nothing: markers make the offsets sparse, and a
    # reorder within the buffer under the version rule applies every latest write.
    source = harness.shipped_source(txn_marker_every=MARKER_EVERY)
    sink = harness.run(source, window=4, buffer=harness.BUFFER, skip_rule="version")

    gap = detect_offset_gaps(source, sink)
    version = reconcile_by_version(source, sink)
    false_alarms = false_alarm_offsets(source, sink)

    return {
        "marker_every": MARKER_EVERY,
        "marker_width": MARKER_WIDTH,
        "offset_gap_alarms": gap.diverged_count,
        "offset_gap_false_alarms": len(false_alarms),
        "version_false_alarms": version.diverged_count,
        "note": (
            "version_false_alarms is structural, not a sampling estimate: the version "
            "reconciler never inspects offsets, so a marker hole can never raise an alarm. "
            "A test pins this invariant."
        ),
    }


def main() -> None:
    figures = run()
    harness.print_table(
        "Experiment C: offset-gap false alarms on a lossless transactional topic",
        [
            ("offset-gap alarms raised", str(figures["offset_gap_alarms"])),
            ("  of which false (marker holes)", str(figures["offset_gap_false_alarms"])),
            ("version reconciler alarms", str(figures["version_false_alarms"])),
        ],
    )
    harness.write("detector_comparison.json", figures)


if __name__ == "__main__":
    main()
