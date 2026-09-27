class OrodError(Exception):
    """Base expected application error."""


class InvalidRepositoryError(OrodError):
    """Repository URL or permissions are invalid."""


class UnsafePathError(OrodError):
    """A path escaped the run workspace or violated a file policy."""


class CommandRejectedError(OrodError):
    """A command was not in the fixed executable allowlist."""


class ScannerOutputError(OrodError):
    """A deterministic scanner failed or returned unusable structured output."""


class PatchRejectedError(OrodError):
    """A generated patch violated safety constraints."""


class RunNotFoundError(OrodError):
    """Requested run does not exist."""


class ReviewNotPendingError(OrodError):
    """A review decision arrived for a run that is not waiting for one."""


class ReviewNotAllowedError(OrodError):
    """A review decision would violate a publishing invariant."""


class WorkspaceIntegrityError(OrodError):
    """The run workspace no longer matches the changes OROD itself applied."""


class RunAlreadyFinishedError(OrodError):
    """An action that needs a live run was requested for a completed or failed run."""


class ScanFailedError(OrodError):
    """No security scanner completed, so the absence of findings means nothing."""


class UnsupportedRepositoryError(OrodError):
    """The repository is not one OROD can analyse, e.g. it contains no Python code."""
