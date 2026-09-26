# ADR 0006: One repository file policy

## Context

Inventory, dependency discovery, source reads and patch validation had separate file
checks. Dependency manifests could follow symlinks outside a workspace, requirements
files had no size limit, and some readers checked links only after resolving them.
Binary files could enter inventory and Git base reads bypassed most working-file rules.

## Decision

`RepositoryFiles` in the adapter layer owns canonical relative-path checks, exclusions,
regular-file checks, a per-file byte limit and strict UTF-8 text decoding. Hidden paths,
ignored build/environment directories, private-key filenames, symlinks, special files,
binary control bytes and invalid UTF-8 are rejected. Tabs, LF, CR and form feed remain
valid text. The configured workspace directory is a trusted anchor; repository root
and descendant components are opened without resolving away their symlinks.

Reads use directory file descriptors with `O_NOFOLLOW`, including every repository
parent component. The final open is nonblocking, so a FIFO can be rejected without
hanging. Metadata comes from the opened descriptor, and the actual read is limited to
`max_file_bytes + 1`, detecting growth after the initial size check. No caller receives
a checked path only to reopen it unsafely.

Inventory and dependency discovery skip rejected entries. Explicit working/base source
requests reject them; patch validation translates policy failures to `PatchRejectedError`.
Patch-specific extension and diff-target restrictions remain additional controls.
Python summaries, residual shell checks, the built-in scanner and container source
copies use the same reader. Fixture copy preserves symlinks for later rejection.

Git base reads first validate the working path, then check the tree entry's regular
file mode and blob size before fetching content. Byte length and text checks prevent
silently truncated or binary output. Because the command port decodes with replacement,
base reads conservatively reject the Unicode replacement character too.

## Consequences

This is a POSIX implementation, matching the project's macOS/Linux support. Inventory
and container input now contain only accepted text files. Repositories requiring binary
fixtures, hidden config or symlinks can fail validation; the policy never relaxes itself
to run their tests. Noncanonical source paths and unsafe direct file requests return
HTTP 400. Deleted or currently unsafe working files cannot be fetched via `revision=base`.

External Bandit/Semgrep processes still have their own file walkers. Extending shared
input filtering to those tools and isolating the whole host-side pipeline remain
separate work. This policy protects adapter reads; it is not a filesystem sandbox for
arbitrary repository code or a transaction covering a later `git apply` invocation.

## Verification

Tests exercise internal/external/broken symlinks, symlink parents/root, replacement
between checking and opening, FIFOs, binary/invalid UTF-8 files, byte boundaries and
growth after stat. All dependency manifest formats are covered, including `requirements`
variants. Tests also cover unsafe Git blobs behind safe working files, fixture copying,
stale inventory records, source summaries, the built-in scanner and container input.
The deterministic corpus and opt-in live Docker test are re-run for this change.
