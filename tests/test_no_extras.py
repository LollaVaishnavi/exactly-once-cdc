"""The core audit must import and run with no optional dependency installed.

A heavy extra present on the build machine can mask a broken import in the job that
installs without it. This runs the whole core path (config, pipeline, reconcile, CLI)
in a subprocess that refuses numpy, playwright and cmarkgfm, so the invariant holds
whether or not those extras happen to be installed. See trap 1 in the CI notes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_RUNNER = textwrap.dedent(
    """
    import sys, importlib.abc
    BLOCKED = {"numpy", "playwright", "cmarkgfm"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError("blocked by no-extras test: " + name)
            return None

    sys.meta_path.insert(0, Blocker())
    from cdc_audit.cli import main
    sys.exit(main(["--policy", sys.argv[1], "--json"]))
    """
)


def test_the_core_path_imports_and_runs_without_optional_extras():
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-c", _RUNNER, str(_REPO_ROOT / "policy.toml")],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO_ROOT),
        check=False,
    )
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}\n{result.stderr}"
    assert '"verdict": "diverged"' in result.stdout


def test_blocking_numpy_actually_takes_effect_in_the_runner():
    # A guard on the guard: confirm the blocker really raises, so a future import of
    # numpy into the core path would fail this test rather than passing unnoticed.
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    probe = "import sys, importlib.abc\n" + _RUNNER.split("from cdc_audit")[0] + "import numpy\n"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "blocked by no-extras test" in result.stderr
