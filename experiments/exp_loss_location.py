"""Experiment B: where does the watermark see loss, and where is it blind?

Question the README asks: is the watermark useless, or blind to one specific shape of
loss? Tail loss, where the newest offsets never arrive, moves the watermark and the
dashboard catches it. Interior loss, where a reordered record below the watermark is
dropped, leaves lag at zero. The metric is honest about loss it can see and loss it
cannot.
"""

from __future__ import annotations

import harness

TAIL_DROPPED = 50


def run() -> dict:
    source = harness.shipped_source()

    # Tail loss: the consumer crashes before the last TAIL_DROPPED records arrive. No
    # reorder, so nothing interior is lost; the gap is purely at the head of the log.
    truncated = source.events[: len(source.events) - TAIL_DROPPED]
    tail_sink = harness.run(
        source, window=0, buffer=harness.BUFFER, skip_rule="offset", delivered=truncated
    )
    tail = harness.measure(source, tail_sink)

    # Interior loss: the shipped scenario.
    interior_sink = harness.run(
        source, window=harness.WINDOW, buffer=harness.BUFFER, skip_rule="offset"
    )
    interior = harness.measure(source, interior_sink)

    return {
        "tail_dropped": TAIL_DROPPED,
        "tail_watermark_lag": tail["watermark_lag"],
        "tail_diverged_keys": tail["diverged_keys"],
        "interior_watermark_lag": interior["watermark_lag"],
        "interior_diverged_keys": interior["diverged_keys"],
    }


def main() -> None:
    figures = run()
    harness.print_table(
        "Experiment B: loss location decides what the watermark sees",
        [
            (
                "tail loss",
                f"dropped {figures['tail_dropped']}, lag {figures['tail_watermark_lag']}, "
                f"{figures['tail_diverged_keys']} keys wrong (dashboard catches it)",
            ),
            (
                "interior loss",
                f"lag {figures['interior_watermark_lag']}, "
                f"{figures['interior_diverged_keys']} keys wrong (dashboard blind)",
            ),
        ],
    )
    harness.write("loss_location.json", figures)


if __name__ == "__main__":
    main()
