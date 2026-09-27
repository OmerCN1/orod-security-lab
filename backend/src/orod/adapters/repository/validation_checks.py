"""The fixed validation checks, and how their output is compared with the base revision.

A check is judged against the same check run on the base revision rather than against
zero: a repository whose tests or lint already fail must not block every patch, while a
patch must never add a failure. Each tool's output is reduced to stable failure
identities without line numbers, because a patch shifts every line below it.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from orod.domain.models import CheckOutcome, CommandResult

# Structured tools can produce large reports; never judge a truncated tail.
CHECK_OUTPUT_CHARS = 2_000_000

COMPILE_ERROR = re.compile(r"^\*\*\* Error compiling '(?P<path>[^']+)'", re.MULTILINE)
PYTEST_FAILURE = re.compile(r"^(?P<kind>FAILED|ERROR) (?P<node>\S+)", re.MULTILINE)
PYTEST_PASSED = re.compile(r"(?P<count>\d+) passed")
# pytest exit codes: 0 passed, 1 tests failed, 5 nothing collected.
PYTEST_RAN = {0, 1}
PYTEST_NOTHING_COLLECTED = 5
CONTAINER_ROOT = "/workspace"


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    args: tuple[str, ...]


# The same checks run twice on one tree - on the base revision, then after the patch -
# often within the same second. Timestamp-validated bytecode would then let the second
# run execute the unpatched code when a patch keeps a file's size, so compileall writes
# hash-checked bytecode and pytest (`-B`) writes none.
CHECKS: tuple[ValidationCheck, ...] = (
    ValidationCheck(
        "compile", ("-m", "compileall", "-q", "--invalidation-mode", "checked-hash", ".")
    ),
    ValidationCheck(
        "ruff",
        ("-m", "ruff", "check", "--select", "F", "--output-format", "json", "--no-cache", "."),
    ),
    # Always run pytest; a repository without `tests/` may keep its tests elsewhere, and
    # "no tests collected" is reported as such rather than as a pass.
    ValidationCheck("pytest", ("-B", "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider")),
)


def interpret(check: ValidationCheck, result: CommandResult, root: Path) -> CheckOutcome:
    outcome = CheckOutcome(
        name=check.name, return_code=result.return_code, timed_out=result.timed_out
    )
    if result.timed_out:
        return outcome.model_copy(update={"parsed": False, "ran": False})
    if check.name == "compile":
        return _compile(outcome, result)
    if check.name == "ruff":
        return _ruff(outcome, result, root)
    return _pytest(outcome, result)


def regressions(baseline: CheckOutcome | None, current: CheckOutcome) -> list[str]:
    """What ``current`` does worse than ``baseline``; empty when it is no worse.

    Without a usable baseline the check must pass outright. Output that could not be
    interpreted, or a timeout, is never tolerated.
    """
    if current.timed_out:
        return ["timed out"]
    if not current.parsed:
        return [f"output could not be interpreted (exit code {current.return_code})"]
    if baseline is None or baseline.timed_out or not baseline.parsed:
        if _passes(current):
            return []
        return sorted(current.failures) or [f"exit code {current.return_code}"]

    introduced = sorted((Counter(current.failures) - Counter(baseline.failures)).elements())
    problems = list(introduced)
    if not problems and _passes(baseline) and not _passes(current):
        problems.append(f"exit code {current.return_code}")
    if (
        baseline.passed_tests is not None
        and current.passed_tests is not None
        and current.passed_tests < baseline.passed_tests
    ):
        missing = baseline.passed_tests - current.passed_tests
        problems.append(f"{missing} fewer passing test(s) than before the patch")
    return problems


def tolerated(baseline: CheckOutcome | None, current: CheckOutcome) -> int:
    """Pre-existing failures that are still present and were allowed through."""
    if baseline is None:
        return 0
    return sum((Counter(current.failures) & Counter(baseline.failures)).values())


def _passes(outcome: CheckOutcome) -> bool:
    if outcome.name == "pytest":
        return outcome.return_code in {0, PYTEST_NOTHING_COLLECTED}
    return outcome.return_code == 0


def _compile(outcome: CheckOutcome, result: CommandResult) -> CheckOutcome:
    text = f"{result.stdout}\n{result.stderr}"
    failing = sorted({match["path"] for match in COMPILE_ERROR.finditer(text)})
    return outcome.model_copy(update={"failures": [f"cannot compile {path}" for path in failing]})


def _ruff(outcome: CheckOutcome, result: CommandResult, root: Path) -> CheckOutcome:
    # Ruff exits 1 when it reports diagnostics and 2 when it could not run.
    if result.return_code not in {0, 1}:
        return outcome.model_copy(update={"parsed": False})
    try:
        diagnostics = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return outcome.model_copy(update={"parsed": False})
    if not isinstance(diagnostics, list):
        return outcome.model_copy(update={"parsed": False})
    failures = [
        f"{item.get('code')} {_relative(str(item.get('filename') or ''), root)} "
        f"{item.get('message')}"
        for item in diagnostics
        if isinstance(item, dict)
    ]
    return outcome.model_copy(update={"failures": sorted(failures)})


def _pytest(outcome: CheckOutcome, result: CommandResult) -> CheckOutcome:
    text = result.stdout
    failures = sorted(
        f"{match['kind'].lower()} {match['node']}" for match in PYTEST_FAILURE.finditer(text)
    )
    tail = text.strip().splitlines()[-1:] if text.strip() else []
    passed_match = PYTEST_PASSED.search(tail[0]) if tail else None
    passed = int(passed_match["count"]) if passed_match else 0
    if result.return_code == PYTEST_NOTHING_COLLECTED:
        return outcome.model_copy(update={"ran": False, "passed_tests": 0})
    if result.return_code in PYTEST_RAN:
        if result.return_code == 1 and not failures:
            # Failed without naming a test: nothing to compare against, so do not trust it.
            return outcome.model_copy(update={"parsed": False, "passed_tests": passed})
        return outcome.model_copy(update={"failures": failures, "passed_tests": passed})
    # Interrupted (collection errors), internal or usage errors: no test ran. Collection
    # errors still name the module, which is what keeps them comparable.
    return outcome.model_copy(
        update={"failures": failures or [f"pytest exit code {result.return_code}"], "ran": False}
    )


def _relative(filename: str, root: Path) -> str:
    for prefix in (str(root), CONTAINER_ROOT):
        if filename.startswith(prefix + "/"):
            return filename[len(prefix) + 1 :]
    return filename
