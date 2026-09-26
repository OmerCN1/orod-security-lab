# OROD — Autonomous Refactoring and Code Security Team

OROD is a local LangGraph multi-agent application that inspects Python GitHub
repositories, consolidates security findings, produces validated fixes and
optionally opens a draft pull request.

## Evaluation

OROD is measured against a controlled vulnerability corpus. 20 hermetic cases (each with
a known vulnerability, an expected finding and an expected outcome) are run through the
real agent pipeline; detection, remediation, policy compliance, latency and cost are reported.

<!-- EVAL_TABLE_START -->

| Model | Detection F1 | Recall | Precision | Auto-fix rate | Patch validity | Policy | Regressions | Median run | Tokens | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `deterministic-baseline` | 1.00 | 100% | 100% | 6% (1/16) | 12% | 2/2 | 0 | 0.2s | 0 | $0.00 |
| `qwen2.5-coder:14b` | 1.00 | 100% | 100% | 6% (1/16) | 12% | 2/2 | 0 | 21.5s | 18,926 | $0.00 |

<!-- EVAL_TABLE_END -->

```bash
make eval                                     # deterministic codemod baseline
make eval MODELS="--model qwen2.5-coder:14b"  # compare a model against the baseline
make eval-list                                # list the corpus
```

The `deterministic-baseline` row shows what the deterministic codemods achieve with no
model at all; subtracting it from a model row leaves the model's net contribution.
Metric definitions, corpus design and the steps for adding a new case are in
`docs/evals.md`; the latest published report is `docs/evals/latest.md`.

## Quick start

Requirements: macOS/Linux, Python 3.12, `uv`, Node.js 22+, Ollama, Git and
GitHub CLI. GitHub repository validation also requires a running local Docker daemon.

```bash
cp .env.example .env
make install
ollama pull qwen2.5-coder:14b
ollama pull nomic-embed-text
```

In two terminals:

```bash
make backend
make frontend
```

UI: <http://localhost:5173> — API: <http://localhost:8000/docs>

`demo://vulnerable-python` is an end-to-end demo repository that needs no network
or GitHub account. For a real GitHub repository and a draft PR, run `gh auth login`
first, then set `OROD_ENABLE_GITHUB_PUBLISH=true` in `.env`.

Before validating a GitHub repository, build the isolated validation image:

```bash
make validation-image
```

In **New scan**, test execution is off by default. Select **I trust this repository
and allow its tests to run** to enable validation. Consent resets when the repository
changes or the dialog is closed/submitted; it is also required for demos. Without
consent, analysis and patch proposals remain available, but validation and publishing
are blocked.

GitHub validation uses an offline, unprivileged container with resource limits and a
temporary copy of the repository. Docker/image failures block validation; there is no
host fallback. The image contains Python, pytest, Ruff and Bandit. Repositories that
need additional dependencies require an operator-built image set with
`OROD_VALIDATION_IMAGE`; dependencies are never installed from repository instructions.
See `docs/decisions/0005-explicit-trust-and-container-validation.md` for the boundary
and the optional Docker integration test.

Ollama structured-output smoke test:

```bash
cd backend
.venv/bin/python ../scripts/verify_ollama.py
```

## Security boundary

Running a repository's tests executes that repository's code and requires explicit
consent. GitHub validation runs in Docker; explicitly trusted, server-owned demo
fixtures run locally. This isolates validation, not the entire application: cloning,
static analysis, OSV queries and publishing still run on the host. The MVP remains
limited to repositories the authenticated GitHub user can push to. OROD never merges
or force-pushes automatically, and never runs LLM output as a shell command.

Architecture and API details live under `docs/`; the working rules for AI agents are
in `AGENTS.md`.

## License

MIT — see `LICENSE`.
