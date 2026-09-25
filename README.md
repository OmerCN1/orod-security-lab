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
GitHub CLI.

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

Ollama structured-output smoke test:

```bash
cd backend
.venv/bin/python ../scripts/verify_ollama.py
```

## Security boundary

The MVP is only for repositories trusted by their owner. Running a repository's tests
executes that repository's code. OROD never merges or force-pushes automatically, and
never runs LLM output as a shell command.

Architecture and API details live under `docs/`; the working rules for AI agents are
in `AGENTS.md`.

## License

MIT — see `LICENSE`.
