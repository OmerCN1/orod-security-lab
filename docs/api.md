# HTTP API

All endpoints are under `/api/v1`.

## Runs

- `POST /runs` — start an analysis; returns HTTP 202. Body accepts
  `repository_url`, optional `base_branch`, `trusted`, and an optional `model`
  identifier that overrides the server default for this run only.
  `trusted` defaults to `false`: setting it to `true` explicitly authorizes execution
  of repository tests. This applies to `demo://` fixtures as well as GitHub repositories.
  GitHub validation always uses an isolated container; consent does not enable host
  execution. Without consent, validation fails closed and a PR cannot be approved/published.
- `GET /runs?limit=&offset=` — run history, most recent first, as compact summaries.
- `GET /runs/{id}` — run status and accumulated artifacts.
- `GET /runs/{id}/events` — Server-Sent Events stream.
- `GET /runs/{id}/files` — safe repository file inventory.
- `GET /runs/{id}/files/content?path=...&revision=working|base` — path-validated text
  file content. `revision=base` returns the file as it was before any patch was applied,
  read from the workspace's `HEAD` commit; it is the left-hand side of the dashboard diff.
  Both revisions reject unsafe paths with HTTP 400: symlinks (including parent
  directories), hidden/ignored paths, special files, binary/non-UTF-8 content and files
  above `OROD_MAX_FILE_BYTES`. The base blob's mode and size are also checked before
  reading it. Inventory and dependency discovery omit files rejected by the same policy.
- `GET /runs/{id}/findings` — normalized security findings.
- `GET /runs/{id}/patch` — patch and validation report.
- `GET /runs/{id}/pull-request` — draft pull-request result.
- `POST /runs/{id}/review` — submit a human decision; returns HTTP 202.
- `POST /runs/{id}/cancel` — cancel an in-process run.

## Review

When `OROD_REQUIRE_HUMAN_APPROVAL` is enabled (the default), a run that reached a
patch decision stops in the `awaiting_review` status and exposes a `review` object
describing what is being asked. The graph is paused on a LangGraph checkpoint, so the
pause survives a backend restart.

`POST /runs/{id}/review` accepts:

```json
{ "decision": "approve" | "reject" | "regenerate", "feedback": "optional text" }
```

- `approve` resumes the graph through the publish node. **Refused with HTTP 422 unless
  validation passed** — the same rule is enforced again in the graph's routing, so no
  path can open a pull request for an unvalidated patch.
- `reject` completes the run without publishing.
- `regenerate` requires `feedback` and sends the developer agent back with that
  instruction. Human revisions are counted separately from the automatic repair budget.

Other responses: `404` when the run does not exist, `409` when the run is not waiting
for a decision (or one is already being applied), `422` for an invalid submission.

## Models

- `GET /models` — models the dashboard may offer. Each entry carries `provider`,
  `available`, and a `detail` explaining why an unavailable model cannot be used.
  Unavailable models are listed rather than hidden.

## Other

- `POST /vulnerability-index/sync` — check OSV and cache advisories.
- `GET /health` — component readiness.

## Streaming

The SSE `id` is the persisted integer event sequence. Clients may reconnect with the
`Last-Event-ID` header, or — since browsers cannot set headers on an `EventSource` —
with the `after` query parameter. The header wins when both are present, because that is
what an automatic browser reconnect sends. The stream replays persisted events from the
cursor before streaming new ones, and ends only when the run reaches a terminal status;
`awaiting_review` is not terminal, so a paused run keeps its stream open.

Completed runs include duration, finding counts by severity, patch/validation success,
repair-attempt count, human revision count, the review decision, and PR creation in the
`metrics` object.
