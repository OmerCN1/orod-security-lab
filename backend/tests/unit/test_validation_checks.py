import json
from pathlib import Path

from orod.adapters.repository.validation_checks import CHECKS, interpret, regressions, tolerated
from orod.domain.models import CheckOutcome, CommandResult

ROOT = Path("/work/run")
CHECK = {check.name: check for check in CHECKS}


def outcome(name: str, return_code: int, stdout: str = "", stderr: str = "") -> CheckOutcome:
    result = CommandResult(argv=[], return_code=return_code, stdout=stdout, stderr=stderr)
    return interpret(CHECK[name], result, ROOT)


def ruff(*diagnostics: tuple[str, str, str]) -> CheckOutcome:
    payload = [
        {"code": code, "filename": f"{ROOT}/{path}", "message": message}
        for code, path, message in diagnostics
    ]
    return outcome("ruff", 1 if payload else 0, json.dumps(payload))


def test_pre_existing_lint_is_tolerated_and_new_lint_is_not() -> None:
    before = ruff(("F401", "app.py", "`os` imported but unused"))
    same = ruff(("F401", "app.py", "`os` imported but unused"))
    worse = ruff(
        ("F401", "app.py", "`os` imported but unused"),
        ("F841", "app.py", "Local variable `x` is assigned to but never used"),
    )

    assert regressions(before, same) == []
    assert tolerated(before, same) == 1
    assert regressions(before, worse) == [
        "F841 app.py Local variable `x` is assigned to but never used"
    ]


def test_container_paths_compare_equal_to_host_paths() -> None:
    host = ruff(("F401", "app.py", "`os` imported but unused"))
    container = outcome(
        "ruff",
        1,
        json.dumps(
            [
                {
                    "code": "F401",
                    "filename": "/workspace/app.py",
                    "message": "`os` imported but unused",
                }
            ]
        ),
    )

    assert host.failures == container.failures


def test_unreadable_ruff_output_is_never_trusted() -> None:
    before = outcome("ruff", 1, "not json")
    assert regressions(before, outcome("ruff", 1, "not json")) != []
    assert regressions(None, outcome("ruff", 2, "", "ruff: error")) != []


def test_pre_existing_failing_test_is_tolerated_but_a_newly_failing_one_is_not() -> None:
    before = outcome("pytest", 1, "FAILED tests/test_a.py::test_old - boom\n1 failed, 3 passed\n")
    same = outcome("pytest", 1, "FAILED tests/test_a.py::test_old - boom\n1 failed, 3 passed\n")
    worse = outcome(
        "pytest",
        1,
        "FAILED tests/test_a.py::test_old - boom\nFAILED tests/test_a.py::test_new - boom\n"
        "2 failed, 2 passed\n",
    )

    assert regressions(before, same) == []
    assert regressions(before, worse) == [
        "failed tests/test_a.py::test_new",
        "1 fewer passing test(s) than before the patch",
    ]


def test_deleting_a_passing_test_is_a_regression() -> None:
    before = outcome("pytest", 0, "4 passed in 0.1s\n")
    after = outcome("pytest", 0, "3 passed in 0.1s\n")

    assert regressions(before, after) == ["1 fewer passing test(s) than before the patch"]


def test_no_collected_tests_passes_but_is_reported_as_not_run() -> None:
    nothing = outcome("pytest", 5, "no tests ran in 0.01s\n")

    assert nothing.ran is False
    assert regressions(nothing, outcome("pytest", 5, "no tests ran in 0.01s\n")) == []


def test_a_failure_that_names_no_test_is_not_trusted() -> None:
    assert outcome("pytest", 1, "something odd\n").parsed is False


def test_collection_errors_are_compared_by_module() -> None:
    before = outcome("pytest", 2, "ERROR tests/test_a.py - ImportError\n1 error in 0.1s\n")
    after = outcome("pytest", 2, "ERROR tests/test_b.py - ImportError\n1 error in 0.1s\n")

    assert before.ran is False
    assert regressions(before, after) == ["error tests/test_b.py"]


def test_compile_failures_are_compared_by_file() -> None:
    before = outcome("compile", 1, "*** Error compiling './broken.py'...\n")
    after = outcome(
        "compile", 1, "*** Error compiling './broken.py'...\n*** Error compiling './app.py'...\n"
    )

    assert (
        regressions(before, outcome("compile", 1, "*** Error compiling './broken.py'...\n")) == []
    )
    assert regressions(before, after) == ["cannot compile ./app.py"]


def test_a_new_failure_without_detail_is_still_caught() -> None:
    assert regressions(outcome("compile", 0), outcome("compile", 1)) == ["exit code 1"]


def test_without_a_baseline_every_check_must_pass() -> None:
    assert regressions(None, ruff()) == []
    assert regressions(None, ruff(("F401", "app.py", "unused"))) == ["F401 app.py unused"]
    assert regressions(None, outcome("pytest", 5, "no tests ran\n")) == []


def test_timeouts_are_never_tolerated() -> None:
    result = CommandResult(argv=[], return_code=124, timed_out=True)
    timed_out = interpret(CHECK["pytest"], result, ROOT)

    assert regressions(timed_out, timed_out) == ["timed out"]
