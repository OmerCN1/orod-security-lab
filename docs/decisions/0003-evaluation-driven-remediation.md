# 3. Evaluation-driven remediation

## Status

Accepted.

## Context

Remediation quality was previously argued from single live runs recorded in
`docs/STATUS.md`. That is not a measurement: it cannot be repeated, it cannot be compared
across models, and it cannot distinguish what the local model contributes from what the
deterministic codemods would have done anyway.

Two properties of the existing code made a measurement impossible:

1. `RoutingLLMProvider` selected the patch provider from the repository **URL scheme**.
   Any `demo://` repository was answered by the deterministic demo codemod and never
   reached the model, so a fixture-based evaluation would have scored the fallback.
2. Providers reported no token or latency usage, so cost could not be attributed to a run.

## Decision

Patch-provider selection is driven by configuration (`OROD_USE_LLM`), not by the
repository URL. Fixture repositories reach the configured model exactly like a cloned
GitHub repository does. Deterministic codemods keep two well-defined roles: they answer
everything when no model is configured, and they act as a repair fallback after a model
patch has failed validation.

`LLMProvider` gains `usage()` / `reset_usage()`, and every adapter records tokens,
latency and failed calls. Prompt construction moves into a single shared module so that
two provider suites differ by model rather than by prompt.

`demo://<slug>` addresses any directory under the configured fixture root, which lets one
running application serve the whole evaluation corpus.

A `backend/evals/` harness replays that corpus through the real graph and reports
detection precision/recall, auto-fix rate, patch validity, policy compliance, regressions,
latency and cost, per model, against a deterministic baseline.

## Consequences

`OROD_USE_LLM=false` is now the explicit offline mode and is what the test suite and the
`demo://vulnerable-python` walkthrough use. Adding a provider means implementing the port
plus a pricing entry; the harness picks it up with no further changes.

The corpus is hermetic by construction - no pinned dependencies, so no live OSV query -
which makes suites comparable but leaves dependency-advisory remediation unmeasured.
Closing that gap needs a recorded OSV fixture.

The harness cross-checks the pipeline rather than trusting it: it rescans each workspace
after the run instead of reading the pipeline's own verdict. That immediately surfaced a
real defect - the post-patch scan was compared against a deduplicated baseline without
being deduplicated itself, so any rule reported by two scanners read as a new high-severity
finding and could block a legitimate pull request. Deduplication is now a shared domain
function used by both.
