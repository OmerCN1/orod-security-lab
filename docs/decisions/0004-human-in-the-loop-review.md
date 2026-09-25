# 4. Human-in-the-loop review

## Status

Accepted.

## Context

The graph ran from clone to pull request without stopping. Whether a draft PR was opened
depended entirely on `OROD_ENABLE_GITHUB_PUBLISH` and on validation passing; a reviewer
could watch the dashboard but could not intervene. For a tool whose whole premise is that
an agent edits your code, "watch it happen" is the wrong level of control — and a patch
that passes every scanner can still be the wrong fix.

## Decision

A `review` node sits between validation and publishing and calls LangGraph's `interrupt`.
The run is parked in a new `awaiting_review` status until a decision arrives at
`POST /runs/{id}/review`: approve, reject, or regenerate with written feedback.

`interrupt` re-executes its node from the top when the graph resumes, so the node must be
idempotent up to the interrupt call. The pending-review announcement is therefore guarded
on the run's own status: only code *after* the interrupt moves the run out of
`awaiting_review`, so the announcement fires exactly once per review round and is skipped
on the resuming pass.

Reviewer feedback travels through the LLM port as a distinct argument rather than being
folded into the existing `previous_error`, because the two mean different things: one is a
machine-detected failure, the other is human intent. It is rendered into the shared prompt
as delimited operator input — above repository content in authority, but still delimited
so it cannot be mistaken for the system prompt.

Human revisions are counted separately from the automatic two-attempt repair budget. A
reviewer asking for another try is not the agent failing.

The publishing invariant is enforced twice: `after_review` refuses to route an approval to
publish when validation did not pass, and `submit_review` rejects such a request before
the graph is resumed at all.

`require_human_approval` defaults to true for the product. Headless callers — the test
suite and the evaluation harness — set it to false explicitly, which keeps the review node
deciding automatically and leaves their behaviour unchanged.

## Consequences

Runs now have a non-terminal waiting state. The SSE stream already terminated only on
`completed`/`failed`/`cancelled`, so a paused run keeps its stream open with no change;
`stream_run_events` and the frontend both treat `awaiting_review` as live.

Because the pause is a LangGraph checkpoint keyed by run id, a review can be answered
after a backend restart.

The frontend needed the pre-patch file content to render a side-by-side diff. A generated
patch is applied but never committed, so `git show HEAD:<path>` supplies it without the
API caching a second copy of every file.

The evaluation harness would hang on every case if it inherited the default: 20 cases
would each sit until their timeout. That coupling is not obvious from the graph code, so
it is stated in `docs/evals.md` and guarded by the corpus run in `make eval`.
