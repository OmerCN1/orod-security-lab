# Project Status

## Current Phase

Phase 9 — Agent-centred dashboard

## Completed

- README rewritten: pipeline stage table, Mermaid architecture diagram with a module
  map, API endpoint and configuration tables, development commands, repository layout
  and current limitations. The eval table markers are unchanged, so `make eval-publish`
  still refreshes it.

- Local API access control (ADR 0011). Non-loopback `Host` headers get 400, requests
  without the bearer token 401, and writes from a foreign `Origin` 403. The token comes
  from `OROD_API_TOKEN` or `data/api-token` (created once, mode 0600). The dashboard
  calls the API same-origin through the Vite proxy, which adds the token server-side,
  so the browser never holds it. Verified against the live stack: direct call without a
  token 401, rebinding host 400 on the API and 403 on Vite, cross-site write 403, the
  dashboard and its event stream working through the proxy.
- A repository without Python source files now fails in the architect stage with an
  explicit message instead of being reported clean; a mostly non-Python repository is
  analysed with a warning, shown on the Architect card.
- CI (`.github/workflows/ci.yml`): backend lint, mypy, tests and the deterministic
  evaluation gated by `python -m evals run --check-baseline ../docs/evals/latest.json`;
  frontend lint, tests, type check and build. Every step was run in a clean copy of the
  tree, which caught seven graph tests broken by the new language check and a test that
  wrote to the real `data/` directory; both fixed.

- Repairs no longer undo the model's own fix. Because every attempt starts from the base
  revision, the B607 codemod used on a repair brought `shell=True` back on the demo
  repository, and the model never got a second attempt. The codemod now steps in only
  when it covers every selected finding (and never on a reviewer regeneration), and the
  model is told that its previous attempt was discarded, what it changed and what
  validation reported. A passing patch being regenerated is no longer described to the
  model as a validation error. `qwen2.5-coder:14b` on the corpus: auto-fix 11/16 -> 14/16,
  zero regressions, deterministic baseline unchanged; published.
- An untrusted run no longer spends a repair attempt: without consent validation refuses
  every patch. The "previous patch reverted" event is a `run` event, so the dashboard no
  longer counts it as an attempt, and a residual finding reported by two scanners is
  named once in the validation summary.

- Models return search/replace edits instead of unified diffs (ADR 0010). The developer
  node applies them to the full workspace files - not the possibly truncated prompt
  excerpt - and renders the diff itself; a missing or ambiguous excerpt rejects the
  proposal, and the rendered diff passes every existing gate. Measured on the corpus with
  `qwen2.5-coder:14b`, same code otherwise: auto-fix 1/16 -> 11/16, patch validity
  6% -> 100%, rejected diffs 16 -> 0, model calls 50 -> 29, median run 22.7 s -> 7.0 s,
  detection and policy unchanged, zero regressions. The deterministic baseline is
  unchanged. Published to `docs/evals/latest.*` and the README table.
- The new-high-finding comparison now matches in two passes - flagged-line text, then
  source/rule/file - so a flagged line the patch edited without fixing counts as
  unresolved rather than also as a regression. Found through the corpus: the model
  swapped `AutoAddPolicy` for the equally insecure `WarningPolicy`; validation already
  refused the patch, but the report counted one regression.

- Baseline-aware validation (ADR 0009). compileall, Ruff `F` and pytest run on the base
  revision before the first attempt and again after each patch; a check fails only when
  the patch adds a failing file, diagnostic or test, or loses passing tests. Pre-existing
  failures are counted in `tolerated_failures`. pytest always runs, and "no tests
  collected" is reported (`tests_ran: false`) instead of passing silently. `bandit -lll`
  and the repository-wide `shell=True` count left validation; the identity-based
  post-patch rescan covers them.
- Running the checks twice exposed stale bytecode: a size-preserving patch applied within
  a second of the baseline ran unpatched code. compileall now writes hash-checked
  bytecode and pytest runs with `-B`.
- A failed scanner is no longer silent. Each scanner's outcome is stored on the run
  (`scanners`, `scan_complete`), named in its event, and shown in the dashboard's
  Security card, findings tab and run history as an incomplete scan rather than "all
  clear". A run in which every code scanner failed ends `failed`.

- Run lifecycle control (ADR 0008). Concurrent review decisions resume the graph once:
  checks and task launch share one coordinator lock, and each decision is tied to the
  review round it answers. A decision that arrives while the pausing task is still
  writing its checkpoint is held and applied instead of being refused with `409`; this
  race also made `test_review_endpoint_rejects_decisions_for_runs_that_are_not_paused`
  flaky.
- `cancel` no longer rewrites completed or failed runs (HTTP 409), is idempotent for
  cancelled ones, and waits up to `OROD_CANCEL_GRACE_SECONDS` for the run's subprocesses
  and containers to be cleaned up before saving `cancelled`. The dashboard refreshes the
  run when a stop is refused, so it shows the real final state.
- `OROD_MAX_CONCURRENT_RUNS` (default 2) bounds executing runs; later runs wait in
  `queued` with a "Waiting for a free run slot" event.
- At startup, runs a previous process left `queued` or `running` are failed as
  interrupted instead of staying in flight forever; paused runs remain resumable.

- Every patch attempt now starts from the base revision (ADR 0007). The previous attempt's
  recorded diff is reversed with `git apply -R` before a repair or regeneration, and a
  patch is refused on a workspace that still carries changes. Attempts used to stack, so
  validation and the dashboard saw their union while the publisher staged only the latest
  proposal's files - a PR could contain a state that was never validated.
- The publisher refuses to commit unless the working-tree diff equals the validated diff
  byte for byte and the changed-file set equals `changed_files`. The workspace diff comes
  from one canonical command that ignores operator Git config and is rejected, not
  truncated, above `OROD_MAX_FILE_BYTES`.
- "No new high/critical finding" compares findings one-to-one by source, rule, file and
  flagged-line text instead of totals, so trading one high finding for another fails.
  OSV is part of the rescan: unchanged manifests reuse the original matches offline,
  changed manifests are re-queried, and an incomplete lookup fails validation. The
  baseline used to include OSV findings the rescan never produced, which masked
  regressions. The eval regression metric uses the same comparison.
- A regenerated patch is now a complete patch of its own; before, the offline provider saw
  its own previous edit and produced nothing to approve.

- Added one `RepositoryFiles` policy for inventory, manifest discovery, source reads,
  patch targets, Python summaries, residual checks, the built-in scanner and container
  copies. Descriptor-relative `O_NOFOLLOW` opens reject symlink files/parents before
  resolution; regular-file, hidden-path, UTF-8/binary and byte-budget checks are shared.
- Dependency discovery no longer follows internal/external manifest symlinks or reads
  oversized/binary requirements. Fixture copies preserve links for policy rejection.
  Git base reads verify the working path plus the original blob mode, size and text
  content (ADR 0006).
- Strict unified-diff target parsing now requires an exact match with `changed_files`.
  Hidden files, symlink components, binary/oversized files, renames, adds/deletes,
  mode changes and ambiguous metadata are rejected before any patch is applied.
- Test consent defaults to false in the dashboard and is forwarded through the API;
  changing the target, closing or submitting the dialog clears consent. Demo preparation
  no longer implicitly grants trust. Missing consent blocks validation and PR approval.
- GitHub validation now uses an injected Docker runner with no host fallback. It uses
  an offline non-root container, read-only root/input, private tmpfs, resource limits,
  filtered temporary source copies and cleanup on timeout/cancellation (ADR 0005).
  `make validation-image` builds the operator-controlled image. Server-owned fixtures
  still run locally only with explicit consent.
- Built the validation image and passed the live Docker integration test: non-root
  execution, no effective capabilities, blocked outgoing connections, excluded hidden
  files, read-only image paths, all four validation commands and no host cache writes.
- Bandit uses Python isolated mode during scanning; subprocess output is bounded while
  draining, and timeout/cancellation reaps the process group.
- Git repository, monorepo, locked Python/Node environments, `AGENTS.md`, and ADRs.
- FastAPI REST API, persisted SSE event log, reconnect support, cancellation, and health checks.
- LangGraph Architect -> Security -> Developer flow with SQLite checkpoints.
- HTTPS GitHub permission/clone adapter and safe Python AST/dependency inventory.
- Built-in AST, Bandit, Semgrep, OSV, Ollama embedding, and Chroma adapters.
- Structured Ollama patch generation plus deterministic offline demo fallback.
- Path/diff/command safety gates, validation commands, and two-attempt repair routing.
- Validation-gated, write-permission-gated GitHub draft PR publisher; no merge/force-push.
- React/Tailwind dashboard with agents, files/source, findings, events, diff, metrics, and PR state.
- `qwen2.5-coder:14b` and `nomic-embed-text` installed locally.
- Live OSV -> Ollama embedding -> Chroma test: 18/18 advisories cached.
- Live demo run: B602 found, patched, compile/Ruff/Bandit/pytest passed, SSE resume verified.
- Real `qwen2.5-coder:14b` Pydantic structured-output smoke test passed.
- Local frontend CORS accepts both `localhost:5173` and `127.0.0.1:5173`.
- Semgrep resolves through the active backend virtual environment instead of relying on shell `PATH`.
- Structured scanner output uses a larger explicit limit; malformed/truncated JSON is reported instead of becoming a silent zero.
- Test-only Bandit B101 assert findings are filtered, OSV emits its own run event, and clean scans skip patch/validation.
- Live rerun against a real-world Python repository: all scanners completed, no actionable finding, no unnecessary patch attempt.
- Low-severity auto-fix policy separates actionable B607 findings from manual-review B101/B311/B404/B603 noise.
- Patch validation rejects no-op diffs, ignores unrelated pre-existing Ruff style debt, and rescans selected findings.
- AST-guided B607 fallback resolves partial executable paths when the local LLM emits an invalid diff.
- Live run against a real GitHub repository remediated B607, passed compile/Ruff/Bandit checks, and opened a draft PR.
- 20-case hermetic evaluation corpus under `backend/evals/cases/`, covering four expected
  outcomes (fix, manual_review, detect_only, clean) across 19 CWEs plus a negative control.
- `python -m evals run` replays the corpus through the real graph, rescans each workspace
  independently, and reports detection precision/recall/F1, auto-fix rate, patch validity,
  policy compliance, regressions, latency, tokens and cost per model.
- `make eval`, `make eval-list`, `make eval-publish`; reports land in
  `docs/evals/latest.{md,json}` and refresh the README comparison table in place.
- Patch-provider routing is configuration-driven instead of URL-scheme-driven, so fixture
  repositories reach the configured model (ADR 0003).
- `LLMProvider` reports token/latency/failure usage; all providers share one prompt module.
- Anthropic adapter behind the existing port, selected by a `claude-*` chat model, with
  structured outputs and per-model pricing in the cost report.
- Offline mode now falls through to the AST codemod, so the deterministic baseline covers
  B607 as well as B602.
- Deterministic baseline recorded: detection F1 1.00 with zero false positives, auto-fix
  1/16, policy 2/2, 0 regressions.
- LangGraph `interrupt` review node: runs pause in `awaiting_review` until a reviewer
  approves, rejects, or regenerates with written feedback (ADR 0004).
- The publishing invariant is enforced twice - in `after_review` and in `submit_review`.
- Reviewer feedback threaded through the LLM port into the shared prompt as delimited
  operator input; human revisions counted apart from the automatic repair budget.
- `GET /runs` history, `GET /models` discovery, `revision=base` file content via
  `git show HEAD:<path>`, optional per-run model through a caching provider registry.
- `list_runs` orders on a numeric `created_at` column added by a guarded bootstrap
  migration; ordering on the JSON timestamp put zero-microsecond records first.
- SSE resume also accepts an `after` query parameter, because browsers cannot set headers
  on an EventSource.
- Three-pane dashboard: control/history, workspace with a side-by-side diff and a sticky
  review bar, and a terminal-style agent trace. Run state extracted into `useRun`.
- Dashboard text is English; design tokens flattened to borders and surface steps.
- Each pipeline stage now emits under its own agent name. Validation and the review pause
  used to be attributed to `developer`, so neither could be shown as a distinct agent; the
  validator also never emitted a completion.
- Bandit findings are titled from `issue_text` rather than the internal `test_name` slug,
  which is what produced titles like `blacklist`.
- Dashboard rebuilt around the team rather than the log: five agents in pipeline order,
  each carrying its role, state, elapsed time, share of the run, and a sentence derived
  from run data; the handoff between them is named on the connector. The work area below
  shows findings and the diff beside the selected agent's steps and raw events.
- Agent state is derived from the run record plus per-agent lifecycle, never from the last
  event alone - which is what left the developer pulsing "working" on a paused run.
- An agent's card only borrows the run record's answer once that agent has completed in
  the *visible* event stream, so a live run and a replay both report what is known so far.
- `Replay run` re-reveals a finished run's events on a compressed clock; because the whole
  dashboard renders from the event list, replay needs no parallel state machine.
- Scanning moved into a `<dialog>`; history became a chip row; the review decision became
  a docked bar that says why approval is locked instead of only greying out.
- The roster is pinned by `roster.realRun.test.ts` against a recorded real run, so a
  backend or frontend change that breaks the narrative fails a test.
- First real-model suite recorded: `qwen2.5-coder:14b` over the full corpus, published
  alongside the deterministic baseline in `docs/evals/latest.md` and the README table.
- Prepared for public release: README translated to English, MIT license added, and local
  machine paths removed from the recorded dashboard fixture.
- The harness now separates "the model returned nothing" from "the model's diff would not
  apply" and counts the latter, because the two call for different fixes.

## In Progress

- None. The review loop and the agent-centred dashboard are implemented and verified end
  to end, including a browser pass over the live stack.

## Next Exact Task

- Dependency remediation: give the developer the manifest/lockfile for selected OSV
  findings, propose the smallest version outside the affected ranges, and include OSV in
  the residual check once a patch can resolve it. Pair it with a recorded OSV fixture so
  the corpus measures it.
- Record an Anthropic suite next to the published qwen row:
  `make eval-publish MODELS="--model qwen2.5-coder:14b --model claude-opus-5"`; it needs
  `OROD_ANTHROPIC_API_KEY`, which is not configured on this machine.
- Review host-side clone/parsing/scanning boundaries before accepting arbitrary hostile
  third-party repositories. Validation isolation is implemented and tested; exercise an
  operator-built dependency image on a representative trusted GitHub repository next.
- Route external Bandit/Semgrep scans through the same filtered repository input;
  their subprocess file walkers are not yet governed by the shared adapter reader.

## Known Issues

- The CI workflow has not run on GitHub yet; its steps were verified locally in a clean
  copy. The Docker isolation test and model suites are not part of CI.
- The dashboard relies on the Vite dev proxy for the API token; a production build
  served without it needs its own token handling.
- The validation image's entrypoint allowlist changed with baseline-aware validation;
  run `make validation-image` again, or GitHub validation fails closed.
- A post-patch scanner failure still fails validation even when the same scanner also
  failed in the initial scan, so a repository scanned with Semgrep offline cannot pass.
- Run control assumes a single backend process owns the database. Queued runs live in
  memory; after a restart they are failed as interrupted rather than resumed.
- The post-patch residual check covers code findings only: dependency remediation is not
  automated, so OSV findings are still "selected" but can never be resolved by a patch.
  They do count toward the new-high-finding gate.
- A scanner that was unavailable during the initial scan but works during the rescan
  makes its findings look new, which fails validation closed.
- The default validation image only includes pytest, Ruff and Bandit; projects needing
  other packages require an operator-maintained image. Hidden config, symlinks, binary
  and oversized files are deliberately excluded from its input copy. Isolation covers
  validation, not the entire host-side analysis pipeline.
- `qwen2.5-coder:14b` still fails 2 of 16 fix cases, both refused by validation rather
  than published: in `hardcoded-password` it imports `os` in the wrong scope, and in
  `hardcoded-tmp-path` its fix breaks an existing test. These are fix-quality failures.
- No Anthropic suite has been recorded; no credential is configured on this machine.
- The corpus is hermetic by design, so the OSV dependency path is exercised by integration
  tests but not by the evaluation corpus.
- `pickle-untrusted-data`, `xml-entity-expansion` and `jinja2-autoescape-disabled` import
  third-party packages that are not installed in the fixture environment; they carry no
  regression tests, so those cases are validated by scanners alone.
- The team strip is a fixed five-column grid inside a fixed-height shell, so on a viewport
  shorter than roughly 900px the work area becomes cramped. `body` keeps its 960px minimum
  width; there is no narrow-viewport layout.
- A Starlette deprecation warning recommends future TestClient migration from `httpx` to `httpx2`.
- External Semgrep rules and live OSV access require network availability; deterministic scanners continue.
- Edits must copy indentation exactly; only trailing whitespace is forgiven. Files with
  CRLF line endings cannot be patched, because the diff parser rejects carriage returns.

## Last Verified Commands

- API access control, language check, CI: `uv run --no-sync pytest -q` — 283 passed,
  1 opt-in Docker test skipped; Ruff and strict mypy (76 source files) passed.
  `npm test -- --run` — 44 passed; lint and build passed. All CI steps also passed in a
  clean copy of the tree; `--check-baseline` reports the baseline matches.
- Repair routing and context: `uv run --no-sync pytest -q` — 265 passed, 1 opt-in Docker
  test skipped. A real `qwen2.5-coder:14b` run of `demo://vulnerable-python` failed with
  B607 unresolved before the change and passed validation on attempt 2 after it.
  `make eval-publish MODELS="--model qwen2.5-coder:14b"` — qwen 14/16, reproduced twice.
- Structured edits: `uv run --no-sync pytest -q` — 258 passed, 1 opt-in Docker test
  skipped; Ruff and strict mypy (73 source files) passed. `npm test -- --run` — 42
  passed; `tsc -b --noEmit` passed.
- `python -m evals run --model qwen2.5-coder:14b` before the change (commit `cbdff93`) and
  after it, then `make eval-publish MODELS="--model qwen2.5-coder:14b"`: see Completed.
- Baseline-aware validation and scan completeness: `uv run --no-sync pytest -q` — 235
  passed, 1 opt-in Docker test skipped. After `make validation-image`,
  `OROD_TEST_CONTAINER=1 ... tests/integration/test_container_runtime.py` — 1 passed.
  The stale-bytecode test fails without the fix. Ruff and strict mypy passed.
- Same change: `npm test -- --run` — 42 passed; ESLint and `tsc -b --noEmit` passed.
- `make eval EVAL_ARGS='--out <scratch>'` — unchanged scores (F1 1.00, auto-fix 1/16,
  patch validity 12%, policy 2/2, zero regressions); median run 0.2 s -> 0.5 s. Only two
  summaries changed wording; `shell-injection` now names the test its patch breaks.
- Run lifecycle control: `uv run --no-sync pytest -q` — 212 passed, 1 opt-in Docker test
  skipped, three consecutive runs; the review-flow e2e file passed ten runs in a row.
  New coordinator tests fail against the previous coordinator (9 of 10 before the round
  tests were added). Ruff and strict mypy (71 source files) passed.
- Same change: `npm test -- --run` — 40 passed; ESLint, `tsc -b --noEmit` and
  `npm run build` passed.
- `make eval EVAL_ARGS='--out <scratch>'` — unchanged deterministic baseline: F1 1.00,
  auto-fix 1/16, patch validity 12%, policy 2/2, zero regressions.
- Attempt isolation and identity-based regressions: `uv run --no-sync pytest -q` — 197
  passed, 1 opt-in Docker test skipped. New tests fail against the previous graph builder.
- Same change: `ruff check src tests evals containers ../scripts/verify_ollama.py` and
  strict mypy (71 source files) passed. Frontend code was unchanged.
- `make eval EVAL_ARGS='--out <scratch>'` — 20/20 cases, unchanged deterministic
  baseline: F1 1.00, auto-fix 1/16, patch validity 12%, policy 2/2, zero regressions.
- Shared file policy: `uv run --no-sync pytest -q` — 178 passed, 1 opt-in Docker
  test skipped in the default run. The live Docker test was run separately and passed.
- Shared file policy: `make lint` — Ruff, strict mypy (70 source files) and frontend
  ESLint passed. `git diff --check` passed. Frontend code was unchanged.
- `make eval EVAL_ARGS='--out /private/tmp/orod-file-policy-eval'` — 20/20 cases,
  unchanged F1 1.00, auto-fix 1/16, patch validity 12%, policy 2/2 and zero regressions.
- Security/trust update: `uv run pytest -q` — 123 passed, 1 opt-in Docker test skipped
  in the default run. After starting Docker and building the image,
  `OROD_TEST_CONTAINER=1 uv run --no-sync pytest -q tests/integration/test_container_runtime.py`
  — 1 passed, including all four real container validation commands.
- Security/trust update: `npm test -- --run` — 39 passed; frontend lint and build passed.
- Security/trust update: `make lint` — Ruff, strict mypy (69 source files), frontend ESLint.
- `make eval EVAL_ARGS='--out /private/tmp/orod-security-review-eval'` — 20/20 cases,
  unchanged deterministic baseline: F1 1.00, auto-fix 1/16, patch validity 12%, policy 2/2,
  zero regressions. Published model comparison preserved.
- `backend/.venv/bin/pytest -q` — 79 passed.
- `backend/.venv/bin/mypy src evals` — passed, strict mode, 67 files.
- `backend/.venv/bin/ruff check src tests evals ../scripts/verify_ollama.py` — passed.
- `npm test -- --run` — 31 passed; `npm run lint`, `tsc -b --noEmit`, `npm run build` clean.
- `python -m evals run` — 20/20 case runs; deterministic baseline unchanged (F1 1.00,
  auto-fix 1/16, 0 regressions), so the agent-attribution change is behaviour-neutral.
- Browser pass over the live stack (Playwright, 1600x1000): a real
  `demo://vulnerable-python` run with `qwen2.5-coder:14b`, every agent panel, the findings
  tab and a full replay - no console errors.
- Live Ollama run through the dashboard: all health components `ok`, run paused for review,
  approval correctly disabled because validation failed.
- Live review loop against `demo://vulnerable-python`: pause, regenerate with feedback,
  reject, and approve all verified over HTTP.
- `cd frontend && npm run lint` — passed.
- `cd frontend && npm test -- --run` — 10 passed.
- `cd frontend && npm run build` — passed.
- `git diff --check` — passed.
- Live `GET /api/v1/health` — all components `ok`.
- Live demo REST/SSE run and safe file-content endpoint — passed.
- Ollama structured-output smoke script — passed.

## Decisions

- Python-only MVP.
- Ollama / `qwen2.5-coder:14b`; embeddings / `nomic-embed-text`.
- OSV package/version matching is authoritative; Chroma is context only.
- Automatic draft PR only for writable repositories; never auto-merge.
- Publishing remains disabled by default until explicitly enabled for a trusted target.
- Explicit test consent for every repository; container-only GitHub validation. The
  wider host-side analysis pipeline is not yet a sandbox for arbitrary hostile repos.
- Provider choice follows the configured chat model; `claude-*` selects the Anthropic
  adapter, anything else selects Ollama.
- Evaluation fixtures are never tuned to improve a result; a gap is fixed in the pipeline
  or recorded as a known issue.
