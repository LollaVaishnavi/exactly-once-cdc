"""Re-measure every published figure and write docs/metrics.json. Nothing is typed by hand.

Why this file exists: a number in a document is only trustworthy if a machine reproduces
it on every build. This collector reads the test count and line coverage from pytest's
own machine-readable reports, re-runs the four experiments, and derives each published
figure from their output. The companion check_numbers.py then fails the build if a
document has drifted from what this produced.

Figures are counts and ratios only. No millisecond, no absolute duration, so every value
here is identical on any machine (receipts rules 5 and 6).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
EXPERIMENTS = ROOT / "experiments"
for _p in (ROOT / "src", EXPERIMENTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exp_detector_comparison  # noqa: E402
import exp_loss_location  # noqa: E402
import exp_sampling_floor  # noqa: E402
import exp_watermark_blind_spot  # noqa: E402


def _run_pytest() -> None:
    REPORTS.mkdir(exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            f"--junitxml={REPORTS / 'junit.xml'}",
            "--cov=cdc_audit",
            "--cov-report=json:" + str(REPORTS / "coverage.json"),
        ],
        cwd=ROOT,
        check=True,
        env={**_env()},
    )


def _env() -> dict:
    import os

    return {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def _tests_total() -> int:
    tree = ET.parse(REPORTS / "junit.xml")
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return sum(int(s.attrib["tests"]) for s in suites)


def _coverage_pct() -> float | int:
    data = json.loads((REPORTS / "coverage.json").read_text(encoding="utf-8"))
    pct = round(data["totals"]["percent_covered"], 1)
    return int(pct) if float(pct).is_integer() else pct


def _whole(value):
    """Collapse a whole-valued float to an int so anchors read cleanly."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def collect(skip_tests: bool) -> dict:
    if not skip_tests:
        _run_pytest()
    elif not (REPORTS / "junit.xml").exists():
        raise SystemExit("reports/junit.xml missing; run without --skip-tests first")

    a = exp_watermark_blind_spot.run()
    b = exp_loss_location.run()
    c = exp_detector_comparison.run()
    d = exp_sampling_floor.run()

    # Keep the committed experiment JSON in step with what is measured here.
    exp_watermark_blind_spot.harness.write("watermark_blind_spot.json", a)
    exp_loss_location.harness.write("loss_location.json", b)
    exp_detector_comparison.harness.write("detector_comparison.json", c)
    exp_sampling_floor.harness.write("sampling_floor.json", d)

    metrics = {
        "tests_total": _tests_total(),
        "coverage_line_pct": _coverage_pct(),
        "events_total": a["scenario"]["events"],
        "keys_total": a["keys_total"],
        "watermark_lag": a["watermark_lag"],
        "records_dropped": a["records_dropped"],
        "harmless_drops": a["records_dropped"] - a["diverged_keys"],
        "diverged_keys": a["diverged_keys"],
        "missing_keys": a["missing_keys"],
        "stale_keys": a["stale_keys"],
        "tail_lag": b["tail_watermark_lag"],
        "tail_diverged_keys": b["tail_diverged_keys"],
        "offset_gap_false_alarms": c["offset_gap_false_alarms"],
        "version_false_alarms": c["version_false_alarms"],
        "p_miss_single_key_at_10pct": _whole(d["p_miss_single_key_at_10pct"]),
        "p_miss_single_key_at_50pct": _whole(d["p_miss_single_key_at_50pct"]),
        "pct_sample_for_95pct_confidence": d["pct_sample_for_95pct_confidence_single_key"],
    }

    anchors = {
        "tests_total": ["{} tests"],
        "coverage_line_pct": ["{}% line coverage", "{} percent line coverage"],
        "events_total": ["{} events"],
        "keys_total": ["of {} keys", "{} keys total"],
        "watermark_lag": ["lag of {}", "lag reads {}", "reports lag {}"],
        "records_dropped": ["{} records", "dropped {}"],
        "harmless_drops": ["{} of those drops"],
        "diverged_keys": ["{} of 500 keys", "{} keys hold", "{} keys diverged"],
        "missing_keys": ["{} missing"],
        "stale_keys": ["{} stale"],
        "tail_lag": ["lag of {}", "lag {}"],
        "tail_diverged_keys": ["{} of 500 keys", "{} keys when the loss is at the tail"],
        "offset_gap_false_alarms": ["{} false alarms", "{} marker holes"],
        "version_false_alarms": ["{} false alarms", "raises {}"],
        "p_miss_single_key_at_10pct": ["misses it {}%", "{}% of the time"],
        "p_miss_single_key_at_50pct": ["{}% of the time", "{} percent"],
        "pct_sample_for_95pct_confidence": ["{}% of the keys", "{} percent of the keys"],
    }

    return {
        "metrics": metrics,
        "anchors": anchors,
        "checked_documents": ["README.md"],
        "note": "every value is produced by running the suite and the four experiments",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-measure published figures")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="read reports/ written by a prior pytest step instead of running pytest here",
    )
    args = parser.parse_args(argv)
    payload = collect(args.skip_tests)
    out = ROOT / "docs" / "metrics.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} with {len(payload['metrics'])} metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
