#!/usr/bin/env python3
"""Run repository tests with bounded, outcome-driven confirmation.

Inputs are the checked-in numeric policy and local test exit statuses. The
runner performs no network requests, reads no remote history, uploads nothing,
and never turns an observed failure into a pass.
"""

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / ".github" / "auto-qa-tuning.json"
TEST_COMMAND = (sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")


@dataclass(frozen=True)
class Policy:
    minimum_clean_runs: int
    post_failure_clean_runs: int
    maximum_runs: int


def _bounded_int(data: dict[str, object], name: str, lower: int, upper: int) -> int:
    value = data.get(name)
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer from {lower} through {upper}")
    return value


def load_policy(path: Path = POLICY_PATH) -> Policy:
    """Load policy and reject settings outside hard safety limits."""
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "version",
        "minimum_clean_runs",
        "post_failure_clean_runs",
        "maximum_runs",
    }
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError(f"policy keys must be exactly: {', '.join(sorted(expected))}")
    if data["version"] != 1:
        raise ValueError("version must be 1")

    minimum = _bounded_int(data, "minimum_clean_runs", 1, 2)
    post_failure = _bounded_int(data, "post_failure_clean_runs", 1, 2)
    maximum = _bounded_int(data, "maximum_runs", 2, 4)
    if maximum < minimum + post_failure:
        raise ValueError("maximum_runs must allow the initial gate and failure confirmations")
    return Policy(minimum, post_failure, maximum)


def run(
    policy: Policy,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> int:
    """Run tests, increasing confirmation rigor after an observed failure."""
    had_failure = False
    clean_run_streak = 0

    for attempt in range(1, policy.maximum_runs + 1):
        required = (
            policy.post_failure_clean_runs if had_failure else policy.minimum_clean_runs
        )
        print(
            f"Auto-QA run {attempt}/{policy.maximum_runs}; "
            f"clean-run threshold {required}",
            file=sys.stderr,
        )
        result = runner(TEST_COMMAND, check=False, cwd=ROOT)
        if result.returncode == 0:
            clean_run_streak += 1
        else:
            had_failure = True
            clean_run_streak = 0

        required = (
            policy.post_failure_clean_runs if had_failure else policy.minimum_clean_runs
        )
        if clean_run_streak >= required:
            if had_failure:
                print(
                    "Auto-QA observed a failure; confirmation runs passed, "
                    "but the original failure remains fatal.",
                    file=sys.stderr,
                )
                return 1
            return 0

    print("Auto-QA did not meet its clean-run threshold.", file=sys.stderr)
    return 1


def main() -> int:
    try:
        policy = load_policy()
    except (OSError, ValueError) as error:
        print(f"Invalid Auto-QA policy: {error}", file=sys.stderr)
        return 2
    return run(policy)


if __name__ == "__main__":
    raise SystemExit(main())
