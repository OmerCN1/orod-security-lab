# Project Status

## Current Phase

Phase 9 — Agent-centred dashboard

## Completed

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

- Record the model suites and publish the comparison table:
  `make eval-publish MODELS="--model qwen2.5-coder:14b --model claude-opus-5"`.
  Requires a running Ollama with `qwen2.5-coder:14b` pulled and/or `OROD_ANTHROPIC_API_KEY`;
  neither was available when the harness was built, so only the baseline row is published.
- Replace unified-diff generation with structured edit operations (search/replace blocks
  or AST-level edits) and re-run `make eval` to measure the before/after. The corpus makes
  this a measurement rather than a claim.
- Add a recorded OSV fixture so dependency-advisory remediation joins the corpus.
- Review host-side clone/parsing/scanning boundaries before accepting arbitrary hostile
  third-party repositories. Validation isolation is implemented and tested; exercise an
  operator-built dependency image on a representative trusted GitHub repository next.
- Route external Bandit/Semgrep scans through the same filtered repository input;
  their subprocess file walkers are not yet governed by the shared adapter reader.

## Known Issues

- The default validation image only includes pytest, Ruff and Bandit; projects needing
  other packages require an operator-maintained image. Hidden config, symlinks, binary
  and oversized files are deliberately excluded from its input copy. Isolation covers
  validation, not the entire host-side analysis pipeline.
- **`qwen2.5-coder:14b` cannot emit a usable unified diff.** Over the 20-case corpus it
  matched the deterministic baseline exactly (auto-fix 1/16) and contributed nothing: 15 of
  16 fix cases ended with `git apply` rejecting the diff as corrupt, and the one success was
  the AST codemod on the second attempt. 50 model calls produced zero exceptions, zero
  schema violations and zero timeouts - the model returns a well-formed `PatchProposal`
  whose `unified_diff` field is not valid diff syntax. This is a format problem, not a
  capability problem, and it is the single highest-value thing to fix next.
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
- General LLM-generated unified diffs can still be malformed; supported rules use deterministic fallback
  codemods, while unsupported invalid patches are safely rejected after two attempts.

## Last Verified Commands

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
