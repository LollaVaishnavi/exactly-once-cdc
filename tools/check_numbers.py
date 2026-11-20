"""Fail the build when a document quotes a figure the code no longer produces.

Why this file exists: machine-measured numbers are only worth something if a document
that drifts from them breaks the build. This loads docs/metrics.json and verifies that
each metric's anchor phrase, the exact wording with the value substituted in, appears in
the checked documents. It matches short anchor phrases rather than bare digits, because a
bare digit is found in a version string or a heading and proves nothing (receipts rules 1
and 3). It also reports any number in the prose that matches no metric, so an unguarded
figure is at least visible.

Exit code 0 means every guarded figure is present and correct. Exit code 1 means a
document has gone stale, which is a build failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Numbers that legitimately appear in prose without being a guarded metric: the scenario
# parameters, small structural counts, the year, and the five ADR indices.
ALLOWED_BARE = {0, 1, 2, 3, 3.11, 4, 5, 8, 10, 15, 16, 25, 40, 48, 50, 64, 100, 500, 2000, 2026}


def _strip_code(text: str) -> str:
    """Remove fenced blocks, inline code spans and HTML attribute values.

    An example invocation is allowed to contain a made-up number; counting it would
    train a reader to ignore the receipts, so code and attributes are excluded from both
    the forward and the reverse check.
    """
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r'\w+="[^"]*"', " ", text)
    # Drop the URL half of a markdown link or image, keeping the visible text, so a
    # badge or ADR link target does not leak its digits into the reverse check.
    text = re.sub(r"\]\([^)]*\)", "] ", text)
    return text


def _normalise(text: str) -> str:
    """Collapse whitespace so an anchor that wraps across a newline still matches."""
    return re.sub(r"\s+", " ", text)


def _anchor_strings(template: str, value) -> list[str]:
    """Every acceptable rendering of one anchor: plain and thousands-grouped."""
    forms = {template.format(value)}
    if isinstance(value, int) and abs(value) >= 1000:
        forms.add(template.format(f"{value:,}"))
    return sorted(forms)


def check(payload: dict) -> tuple[list[str], list[str]]:
    metrics = payload["metrics"]
    anchors = payload["anchors"]
    docs = payload["checked_documents"]

    corpus_parts = []
    for name in docs:
        corpus_parts.append(_normalise(_strip_code((ROOT / name).read_text(encoding="utf-8"))))
    corpus = " ".join(corpus_parts)

    failures: list[str] = []
    for key, value in metrics.items():
        templates = anchors.get(key)
        if not templates:
            failures.append(f"metric {key!r} has no anchor; every figure must be guarded")
            continue
        candidates = [s for t in templates for s in _anchor_strings(t, value)]
        if not any(c in corpus for c in candidates):
            failures.append(
                f"metric {key!r} = {value}: no anchor found. Expected one of: "
                + " | ".join(candidates)
            )

    # Reverse check: a number in the prose that matches no metric value. Compared
    # numerically, so "001" from an ADR link and "100" from a metric are judged by value.
    known_values = {float(v) for v in metrics.values()} | {float(n) for n in ALLOWED_BARE}
    unguarded: list[str] = []
    for token in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", corpus):
        cleaned = token.rstrip(",.").replace(",", "")
        if not cleaned:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if value not in known_values:
            unguarded.append(cleaned)

    return failures, sorted(set(unguarded), key=float)


def main(argv: list[str] | None = None) -> int:
    path = ROOT / "docs" / "metrics.json"
    if not path.exists():
        print("docs/metrics.json missing; run tools/collect_metrics.py first", file=sys.stderr)
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    failures, unguarded = check(payload)

    if unguarded:
        print("note: prose numbers matching no metric (not a failure): " + ", ".join(unguarded))

    if failures:
        print("\nFAIL: documents have drifted from the measured figures:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"OK: all {len(payload['metrics'])} guarded figures match the checked documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
