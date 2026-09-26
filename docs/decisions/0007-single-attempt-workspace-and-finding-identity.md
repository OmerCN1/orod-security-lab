# ADR 0007: One attempt per workspace state; findings compared by identity

## Context

Repair attempts and reviewer regenerations were applied on top of the previous attempt.
The stored diff was the whole working tree, so validation and the dashboard saw the union
of every attempt, while the publisher staged only the latest proposal's `changed_files`.
A pull request could therefore contain a state that was never validated.

The "no new high/critical finding" gate compared totals. A patch that removed one high
finding and introduced another passed as neutral, and the baseline included OSV findings
that the post-patch rescan never produced, so vulnerable dependencies masked regressions.

## Decision

Each developer attempt starts from the base revision. The previous attempt's recorded
diff is reversed with `git apply -R`; any other working-tree difference is an integrity
failure, not something to clean up, so no destructive Git command is introduced. A patch
is refused on a workspace that still carries changes. The workspace diff is produced by
one canonical command that ignores operator Git configuration, and is rejected rather
than truncated when it exceeds the byte limit.

Before committing, the publisher requires the working-tree diff to equal the validated
diff byte for byte and the changed-file set to equal `changed_files`.

Post-patch validation matches high/critical findings one-to-one on source, rule, file and
the whitespace-normalised text of the flagged line, read from the base revision for the
original findings and from the working tree for the rescan. Line numbers are excluded
because a patch shifts them. Dependencies are rediscovered after the patch: unchanged
manifests reuse the original OSV matches without network access, changed manifests are
queried again, and an incomplete OSV lookup fails validation. The evaluation harness uses
the same comparison for its regression metric.

## Consequences

A second attempt no longer sees the first attempt's edits; it receives the base sources and
the previous validation error. A patch that re-edits a line carrying an unselected high
finding counts that finding as new and fails closed; today every high finding is
selected, so the residual check would reject that patch anyway.

The residual check still covers code findings only, because dependency remediation is not
automated: including OSV there would fail every patch in a repository with a vulnerable
dependency. A scanner that was unavailable during the initial scan but works during the
rescan makes its findings look new, which also fails closed.
