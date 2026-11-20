"""Experiment A: does a zero-lag watermark mean the sink is correct? No.

Question the README asks: on the shipped stream, what does the consumer-lag dashboard
report, and how many rows are actually wrong behind that number? This is the headline:
the watermark reads caught up while rows are silently missing or stale.
"""

from __future__ import annotations

import harness


def run() -> dict:
    source = harness.shipped_source()
    sink = harness.run(source, window=harness.WINDOW, buffer=harness.BUFFER, skip_rule="offset")
    figures = harness.measure(source, sink)
    figures["scenario"] = {
        "seed": harness.SEED,
        "keys": harness.KEYS,
        "events": harness.EVENTS,
        "reorder_window": harness.WINDOW,
        "commit_interval": harness.BUFFER,
    }
    return figures


def main() -> None:
    figures = run()
    harness.write("watermark_blind_spot.json", figures)
    harness.print_table(
        "Experiment A: the watermark blind spot",
        [
            ("watermark lag (dashboard)", str(figures["watermark_lag"])),
            ("records dropped", str(figures["records_dropped"])),
            ("keys diverged", f"{figures['diverged_keys']} of {figures['keys_total']}"),
            ("  missing", str(figures["missing_keys"])),
            ("  stale or wrong", str(figures["stale_keys"])),
        ],
    )


if __name__ == "__main__":
    main()
