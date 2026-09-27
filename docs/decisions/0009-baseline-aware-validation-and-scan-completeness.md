# ADR 0009: Baseline-aware validation; a failed scanner is not a clean scan

## Context

Validation required every check to pass outright. A repository whose tests already
failed, or which already had a Ruff `F` diagnostic, a high Bandit finding or any
`shell=True`, could never pass, whatever the patch did. pytest ran only when a `tests/`
directory existed, so a repository keeping its tests elsewhere passed without running
them, and one without tests passed with no sign that nothing ran.

A scanner that raised was reported only as a warning event without a scanner name. The
dashboard counted the scanners that worked, and a run whose scanners all failed
completed as a clean repository.

## Decision

The fixed checks - `compileall`, Ruff `F` and pytest - run once on the untouched base
revision before the first patch attempt, and again after each patch. Each tool's output
is reduced to failure identities without line numbers (failing file; rule, file and
message; test id), and a check passes when the patch introduces no new identity and does
not reduce the number of passing tests. Unparseable output and timeouts always fail;
without a baseline every check must pass outright. pytest always runs and "no tests
collected" is recorded as `tests_ran: false`.

`bandit -lll` and the repository-wide `shell=True` count are no longer validation checks.
The post-patch security rescan compares every scanner's high/critical findings by
identity with the originals (ADR 0007), which is what those two approximated.

Because the checks run twice on one tree, often within a second, compileall writes
hash-checked bytecode and pytest runs with `-B`. Timestamp-validated bytecode from the
baseline run otherwise let the second run execute unpatched code when a patch kept a
file's size.

Every scanner's outcome is stored on the run (`scanners`, `scan_complete`) and emitted
with its name. Any failure marks the scan incomplete, which the run summary, completion
message and dashboard state. If every code scanner fails, the run fails.

## Consequences

Validation runs the checks twice, so a trusted run takes longer; the deterministic
corpus median rose from 0.2 s to 0.5 s with unchanged scores. The validation image's
entrypoint allowlist changed, so `make validation-image` must be re-run; an old image
fails validation closed. A patch that fixes a pre-existing failure is not credited, only
never penalised.
