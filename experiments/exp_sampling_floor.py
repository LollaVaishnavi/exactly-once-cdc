"""Experiment D: what does a memory-bounded, sampled reconciler fail to catch?

Question the README asks: the version reconciler costs O(keys) memory. If a deployment
can only afford to inspect a fraction of keys, what loss slips through? The answer is a
detection floor: a loss confined to few keys is likely missed, and the probability is
exact, so the claim is priced at the sample it would actually need.

P(miss all L lost keys while sampling s of K without replacement) = C(K-L, s) / C(K, s).
The closed form is published. When numpy is installed it is cross-checked by a seeded
Monte Carlo, printed but not published, so the headline stays deterministic.
"""

from __future__ import annotations

from math import comb

import harness

FRACTIONS = (0.10, 0.25, 0.50, 1.00)
LOSS_SIZES = (1, 5, 40)
SHIPPED_LOSS = 40


def p_miss(keys_total: int, loss: int, sample: int) -> float:
    """Exact probability a sample of `sample` keys contains none of `loss` lost keys."""
    if sample > keys_total - loss:
        return 0.0
    return comb(keys_total - loss, sample) / comb(keys_total, sample)


def _fraction_for_confidence(keys_total: int, loss: int, confidence: float) -> int:
    """Smallest integer percent sample that catches `loss` with at least `confidence`."""
    for percent in range(1, 101):
        sample = round(keys_total * percent / 100)
        if 1 - p_miss(keys_total, loss, sample) >= confidence:
            return percent
    return 100


def _pct(value: float) -> float | int:
    """Round to one decimal, and collapse a whole number to an int for tidy anchors."""
    rounded = round(value * 100, 1)
    return int(rounded) if float(rounded).is_integer() else rounded


def run() -> dict:
    k = harness.KEYS
    table = {}
    for loss in LOSS_SIZES:
        for frac in FRACTIONS:
            sample = round(k * frac)
            key = f"loss{loss}_frac{int(frac * 100)}"
            table[key] = _pct(p_miss(k, loss, sample))

    return {
        "keys_total": k,
        "shipped_loss": SHIPPED_LOSS,
        "p_miss_single_key_at_10pct": _pct(p_miss(k, 1, round(k * 0.10))),
        "p_miss_single_key_at_50pct": _pct(p_miss(k, 1, round(k * 0.50))),
        "pct_sample_for_95pct_confidence_single_key": _fraction_for_confidence(k, 1, 0.95),
        "p_miss_table_percent": table,
    }


def _monte_carlo_note(keys_total: int, loss: int, frac: float) -> str:
    """Cross-check the closed form with a seeded Monte Carlo, if numpy is available.

    The result is printed, never written to JSON, so the published figures stay exact
    and identical whether or not the experiments extra is installed.
    """
    try:
        import numpy as np
    except ModuleNotFoundError:
        return "monte-carlo cross-check skipped (numpy not installed)"

    rng = np.random.default_rng(harness.SEED)
    sample = round(keys_total * frac)
    lost = set(range(loss))
    trials = 20000
    misses = 0
    for _ in range(trials):
        drawn = rng.choice(keys_total, size=sample, replace=False)
        if lost.isdisjoint(drawn.tolist()):
            misses += 1
    empirical = misses / trials
    closed = p_miss(keys_total, loss, sample)
    agrees = abs(empirical - closed) < 0.02
    return (
        f"monte-carlo check (L={loss}, frac={frac}): empirical {empirical:.3f} vs "
        f"closed {closed:.3f} -> {'agrees' if agrees else 'DISAGREES'}"
    )


def main() -> None:
    figures = run()
    harness.print_table(
        "Experiment D: the detection floor of a sampled reconciler",
        [
            (
                "miss a 1-key loss, sampling 10%",
                f"{figures['p_miss_single_key_at_10pct']}%",
            ),
            (
                "miss a 1-key loss, sampling 50%",
                f"{figures['p_miss_single_key_at_50pct']}%",
            ),
            (
                "sample needed for 95% confidence (1-key loss)",
                f"{figures['pct_sample_for_95pct_confidence_single_key']}% of keys",
            ),
        ],
    )
    print("  " + _monte_carlo_note(harness.KEYS, 1, 0.10))
    harness.write("sampling_floor.json", figures)


if __name__ == "__main__":
    main()
