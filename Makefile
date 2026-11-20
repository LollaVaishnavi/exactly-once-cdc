# cdc-audit. `make verify` is the one command the README promises a reviewer: it runs
# offline, from a fresh clone, and is byte-identical on re-run. Keep it that way.

PYTHON ?= python3
export PYTHONPATH := src

.PHONY: lint test receipts verify experiments evidence clean

lint:
	ruff check src tests experiments tools

test:
	mkdir -p reports
	$(PYTHON) -m pytest -q --junitxml=reports/junit.xml \
		--cov=cdc_audit --cov-report=json:reports/coverage.json --cov-report=term-missing

# Re-measure every figure, then fail the build if any document drifted from it. Uses the
# reports/ written by `make test` when present, so verify does not run the suite twice.
receipts:
	$(PYTHON) tools/collect_metrics.py --skip-tests
	$(PYTHON) tools/check_numbers.py

verify: lint test receipts

# Re-run the four experiments, writing their JSON to docs/experiments/ and printing tables.
experiments:
	$(PYTHON) experiments/exp_watermark_blind_spot.py
	$(PYTHON) experiments/exp_loss_location.py
	$(PYTHON) experiments/exp_detector_comparison.py
	$(PYTHON) experiments/exp_sampling_floor.py

# Dev-time only, needs the evidence extras (playwright, cmarkgfm) and a browser. Never
# part of verify, so CI stays pure-Python and the no-extras install path is exercised.
evidence:
	$(PYTHON) tools/render_diagrams.py
	$(PYTHON) tools/capture_screenshots.py
	$(PYTHON) tools/record_demo.py

clean:
	rm -rf reports .pytest_cache .ruff_cache **/__pycache__ *.egg-info src/*.egg-info
