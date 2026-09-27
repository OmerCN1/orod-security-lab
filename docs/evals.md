# Evaluation harness

The harness replays a corpus of controlled vulnerability fixtures through the real
LangGraph pipeline and scores what came out. It is the answer to the only question that
matters about an autonomous remediation agent: *how often is it actually right, and what
did that cost?*

```bash
make eval                                                  # deterministic baseline only
make eval MODELS="--model qwen2.5-coder:14b"               # one model vs the baseline
make eval MODELS="--model qwen2.5-coder:14b --model claude-opus-5"
make eval-publish MODELS="--model claude-opus-5"           # also refresh docs/evals/latest.*
make eval-list                                             # show the corpus
```

The latest published run is in [`docs/evals/latest.md`](evals/latest.md).

## What a case is

Each case is a self-contained Python repository plus a manifest stating what the pipeline
owes it.

```text
backend/evals/cases/<case-id>/
  case.json     expectations
  repo/app.py   the vulnerable module
  repo/tests/   optional regression guard
```

```json
{
  "id": "shell-injection",
  "cwe": "CWE-78",
  "expected_outcome": "fix",
  "expected_findings": [{"rule_id": "B602", "file_path": "app.py", "severity": "high"}],
  "allowed_extra_rules": ["B404"],
  "rationale": "Argument list execution removes the shell without changing the output."
}
```

`expected_outcome` separates what the pipeline must *do* from what it must merely *see*:

| Outcome | The pipeline must |
|---|---|
| `fix` | produce a patch that passes validation and clears the finding |
| `manual_review` | report the finding and **decline** to patch it, per the routing policy |
| `detect_only` | report the finding; no safe stdlib remediation exists, so patching is unscored |
| `clean` | report nothing and patch nothing - a negative control for false positives |

`allowed_extra_rules` lists rules that legitimately co-occur (for example `B404`,
"subprocess imported", next to `B602`). Anything reported that is neither expected nor
tolerated is a false positive, which is what makes the `clean` control meaningful.

Fixture tests are **regression guards, not fix assertions**: they must pass on both the
vulnerable and the remediated code. Whether the vulnerability was actually removed is
decided by an independent post-run rescan, never by the fixture's own tests.

## Metrics

**Detection** - findings are matched on `(rule_id, file_path)`; line numbers are ignored so
a scanner upgrade that shifts a line does not read as a miss.

- `recall` = expected findings reported / expected findings
- `precision` = expected findings reported / all reported findings that are not tolerated
- `f1` = harmonic mean of the two

**Remediation**

- `auto-fix rate` - `fix` cases whose patch validated *and* whose finding is gone from an
  independent rescan, over all `fix` cases
- `patch validity rate` - cases where a generated patch applied cleanly (for a model,
  the diff rendered from its edits), over cases where
  generation was attempted; this isolates malformed-diff failures from wrong-fix failures
- `policy` - `manual_review` cases where the pipeline correctly declined to patch
- `regressions` - cases where the patch introduced a new high or critical finding. Findings
  are matched one-to-one by source, rule, file and the text of the flagged line (not by
  totals), using the same function as the pipeline's own validation gate

**Cost** - token counts come from the provider's own usage metadata. Locally hosted models
report `$0.00`; hosted models are priced from the table in `evals/metrics.py`. An
unrecognised hosted model reports `unknown` rather than silently claiming it was free.

## Headless mode

The harness sets `require_human_approval=False`. The product pauses before publishing and
waits for a human decision (ADR 0004); a suite that inherited that default would interrupt
on every case and sit until its timeout, turning a 20-second run into hours. `make eval`
is the guard: if a graph change breaks this, the corpus run stops finishing in seconds.

## Why the corpus is hermetic

No case declares a pinned dependency, so the OSV adapter short-circuits before any HTTP
call; external scanners and GitHub publishing are disabled; every stateful path is
redirected into a scratch directory that is deleted afterwards. A suite therefore produces
the same numbers offline, in CI, and on a laptop - which is the only way two model runs
are comparable.

The cost of that choice is that dependency-advisory remediation (the OSV path) is **not**
covered by the corpus. Adding it needs either a recorded OSV fixture or an accepted
network dependency; it is the clearest next gap.

## Adding a case

1. Create `backend/evals/cases/<case-id>/repo/app.py` with exactly one intended defect.
2. Add `tests/test_app.py` only if the behaviour survives a correct fix.
3. Run the scanners to see what actually fires, rather than guessing the rule id:
   `cd backend && uv run python -m evals run --case <case-id>`
4. Write `case.json` from the observed output, then re-run until the baseline result is
   the one you intended.

`tests/unit/test_eval_corpus.py` enforces the corpus invariants: unique ids, a `repo/`
directory, a stated rationale, no pinned dependencies, and coverage of all four outcome
kinds.

## Model comparison validity

Every provider is given the byte-identical prompt from `orod/adapters/llm/prompts.py`, so
a difference between two suites is a difference between models rather than between
adapters. Fixture repositories reach the configured model like any other repository; the
deterministic codemods are a *fallback*, not a shortcut, and they answer on their own only
when `OROD_USE_LLM=false`. That is what the `deterministic-baseline` suite measures, and
subtracting it from a model suite gives the model's actual contribution.
