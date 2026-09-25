# Roadmap

## Phase 0 — Foundation

Monorepo, locked Python/Node environments, project contracts, health checks,
CI-ready commands, and AI handoff documentation.

## Phase 1 — Vertical slice

Architect, Security, and Developer LangGraph flow; persisted events and
checkpoints; FastAPI REST/SSE; React live dashboard; deterministic offline demo.

## Phase 2 — Repository intelligence

Authenticated GitHub metadata/clone, Python AST inventory, dependency discovery,
path and file limits, and repository summary.

## Phase 3 — Security and RAG

Built-in AST checks, Bandit, Semgrep, OSV package/version matching, Chroma
advisory cache, and Ollama embeddings. OSV is authoritative; RAG supplies only
compact explanatory/remediation context.

## Phase 4 — Remediation

Structured Ollama patch generation, strict unified-diff validation, two-attempt
repair routing, compile/Ruff/Bandit/pytest gates, and no-new-high checks.

## Phase 5 — GitHub publishing

Idempotent run branch, explicit file staging, validation-gated push, and draft
PR creation through GitHub CLI. No merge or force-push capability.

## Phase 6 — Product dashboard

Repository tree, agent state, persisted event timeline, finding cards, diff,
validation summary, health status, cancellation, and draft PR link.

## Phase 7 — Evaluation and hardening

A 20-case hermetic vulnerability corpus, a harness that replays it through the real
graph, and per-model reporting of detection precision/recall, auto-fix rate, patch
validity, policy compliance, regressions, latency and cost against a deterministic
baseline. Provider-agnostic model adapters behind one port so local and hosted models are
compared on an identical prompt. See `docs/evals.md`.

## Phase 8 — Isolation and breadth

Container or microVM isolation for arbitrary third-party repositories, a recorded OSV
fixture so dependency remediation joins the corpus, structured edit operations in place of
raw unified diffs, and the first authenticated sandbox-repository PR trial.
