# ADR 0010: Models return edits; the application renders the diff

## Context

Models were asked for a unified diff. On the 20-case corpus `qwen2.5-coder:14b` returned
schema-valid responses for every call, yet 16 of 17 patch attempts were rejected as
malformed ("truncated patch hunk", "invalid patch hunk"); its only success came from the
deterministic AST codemod. The hunk counts and context lines of a diff are exactly what
language models get wrong, and the prompt's source excerpts can be truncated, so even a
well-formed diff could be computed against text the model never saw in full.

## Decision

The shared prompt asks for `EditProposal`: a list of `{path, search, replace}` edits, an
explanation and finding ids. Model-backed providers carry the edits in `PatchProposal`
with an empty diff. The developer node applies them to the full files, read under the
repository file policy, and only to files the model was given. Each `search` must occur
exactly once, first as an exact excerpt, then as whole lines ignoring trailing
whitespace; indentation is never guessed. A missing, ambiguous, empty or no-op edit
rejects the proposal. The application renders the diff, including files without a final
newline, and that diff passes the unchanged gates: strict target parsing, changed-file
matching, size limits, `git apply --check`, validation and the post-patch scan.

Deterministic codemods still return diffs.

Measuring the change surfaced a flaw in ADR 0007: a flagged line that a patch edited
without fixing no longer matched by line text and was counted as introduced. Findings
left unmatched are now matched again by source, rule and file.

## Consequences

Measured with `qwen2.5-coder:14b` on the same corpus and code otherwise: auto-fix 1/16 to
11/16, patch validity 6% to 100%, rejected diffs 16 to 0, model calls 50 to 29, median
run 22.7 s to 7.0 s, detection and policy unchanged, zero regressions. The remaining five
failures were wrong fixes that validation refused, not format errors.

Repairs then had to change with it. Each attempt starts from the base revision (ADR
0007), so the B607 codemod that used to answer every repair discarded the model's
earlier, partly correct fix. The codemod now answers a repair only when it covers every
selected finding, and the model is told that its previous attempt was discarded, what it
changed and why validation refused it. That raised the same model to 14/16 with zero
regressions; the two remaining failures are again wrong fixes that validation refused. The result does
not show that a model's fixes are correct; validation and review still decide that.

Edits must reproduce indentation exactly, and CRLF files remain unpatchable because the
diff parser rejects carriage returns.
