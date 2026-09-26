# ADR 0005: Explicit test consent and isolated GitHub validation

## Context

The dashboard submitted `trusted: true` for every run, and fixture preparation also
promoted demos to trusted. GitHub validation executed project tests on the operator's
machine. An argv allowlist does not isolate Python code executed by pytest.

## Decision

- Default consent to false in both the API and dashboard. Never upgrade trust during
  preparation. Reset dashboard consent when changing a target, closing or submitting
  the dialog. Analysis and proposed patches do not grant permission to execute tests.
- Require consent before running any validation command. Server-owned fixtures with
  `LOCAL` permission may run locally after consent. Every other snapshot uses the
  injected `CommandRunner` for container validation, without a host fallback.
- Compose `ContainerCommandRunner` in the application bootstrap. Its commands are
  restricted to the existing compileall/Ruff/Bandit/pytest argv sequences.
- Run Docker without networking, host credentials, privileges or writable host mounts.
  Use a non-root UID, dropped capabilities, no-new-privileges, a read-only root,
  resource limits and private tmpfs. Mount a filtered temporary copy read-only and
  copy it into disposable container storage. Exclude hidden files/directories,
  symlinks, special files and common private-key filenames; cap input size/count.
- Use an operator-built image, `orod-validation:local` by default, with `--pull=never`.
  Missing dependencies fail validation. No package install, build script, shell command
  or image choice comes from the model or repository.
- Remove the named container on completion, timeout and cancellation. Bound command
  output during collection and disable Docker logging to limit output-based exhaustion.
- Bandit static scanning uses `python -I` to avoid module shadowing from the repo.

## Consequences and limits

Docker must be running locally for GitHub validation. Build the default image with
`make validation-image`. A custom image can supply additional project dependencies
via `OROD_VALIDATION_IMAGE`; it is operator-controlled and must retain the validation
entrypoint contract. Hidden config and symlinks are omitted from validation input,
so repositories depending on them may fail validation. Each command gets a fresh copy.

This decision isolates validation only, not host-side clone, parsing, OSV queries,
external static scanners or publishing. It does not remove GitHub push-permission
requirements or authorize tests without consent. Containers share the daemon host
kernel; arbitrary hostile-repository support still needs a wider isolation review.

## Verification

Unit tests cover consent, fixture trust preservation, no host fallback, sandbox
options, filtered inputs and cleanup. API defaults and frontend request payloads are
tested. The runtime integration check is opt-in and requires a built image:

```bash
make validation-image
cd backend
OROD_TEST_CONTAINER=1 uv run pytest -q tests/integration/test_container_runtime.py
```

The runtime check verifies non-root execution, dropped capabilities, excluded hidden
files, read-only image paths, blocked outgoing connections and no host pytest cache.
It also executes all four validation commands through the repository adapter. The
default image was built and this check passed during implementation.
