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
