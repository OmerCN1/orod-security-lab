# HTTP API

All endpoints are under `/api/v1`.

## Access

Every endpoint requires `Authorization: Bearer <token>`; `/openapi.json` and `/docs`
do not. The token is `OROD_API_TOKEN` or, when that is empty, the contents of
`data/api-token`, which the backend creates on first start with mode 0600. Requests
whose `Host` is not in `OROD_ALLOWED_HOSTS` (default `localhost`, `127.0.0.1`) get `400`,
missing or wrong tokens get `401`, and a write (`POST`) carrying an `Origin` other than
the dashboard's gets `403`.

The dashboard never holds the token: its dev server proxies `/api` to the backend and
adds the header there, so the browser calls the API same-origin. For `curl`, read the
token from the file, e.g. `scripts/demo.sh`; in `/docs`, paste it into **Authorize**.

## Runs

- `POST /runs` — start an analysis; returns HTTP 202. A repository without Python source
  files fails in the architect stage with an "OROD analyses Python repositories only"
  error instead of reporting a clean scan; one that is mostly another language is
  analysed with a warning that only its Python files are covered. Body accepts
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
- `GET /runs/{id}/findings` — normalized security findings. The run record also carries
  `scanners` (one `{name, ok, findings, detail}` entry per scanner, OSV included) and
  `scan_complete`, which is `false` when any scanner failed: an empty findings list is
  then not a clean result. A run in which every code scanner failed ends `failed`.
  OSV findings also carry `dependency` (the matched `{name, version, source_file,
  ecosystem}`) and `fixed_versions` (the advisory's fixed releases for that package);
  both are `null`/empty for code findings. An advisory is selected for remediation only
  when a pin change can resolve it (ADR 0012).
- `GET /runs/{id}/patch` — patch and validation report. A patch that upgrades pinned
  dependencies names them in its `explanation`, and its `patch` event payload lists them
  under `dependency_upgrades` (`name`, `current_version`, `target_version`,
  `advisory_ids`, `finding_ids`).
- `GET /runs/{id}/pull-request` — draft pull-request result.
- `POST /runs/{id}/review` — submit a human decision; returns HTTP 202.
- `POST /runs/{id}/cancel` — cancel a queued, running or paused run. A running run is
  stopped and awaited for up to `OROD_CANCEL_GRACE_SECONDS` so its process groups and
  validation containers are gone before `cancelled` is saved. Cancelling a cancelled run
  returns it unchanged; a completed or failed run is never rewritten and returns `409`.

## Run lifecycle

At most `OROD_MAX_CONCURRENT_RUNS` runs execute at once; further runs stay `queued` and
receive a "Waiting for a free run slot" event. A resumed review takes a slot as well.
When the backend starts, runs a previous process left `queued` or `running` are marked
`failed` with an "interrupted" error, because their tasks died with that process. Runs
in `awaiting_review` are left alone: their graph is parked on a checkpoint.
This assumes a single backend process owns the database.

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
Decisions are matched to the review round they answer, so concurrent submissions resume
the graph once: the second receives `409`. A decision that arrives while the run is still
finishing its pause is held until the pause completes, then applied.

## Validation

Validation runs three fixed checks - `compileall`, Ruff `F` rules and pytest - first on
the untouched base revision, then on the patched tree. A check passes when the patch adds
nothing the base revision did not already have: no newly failing file, diagnostic or
test, and no fewer passing tests. Pre-existing failures are reported in
`validation.tolerated_failures` instead of blocking every patch. pytest always runs;
`validation.tests_ran` is `false` when it collected no tests, and the summary says so.
Output that cannot be interpreted and timeouts always fail. Security regressions are
judged by the post-patch scan (ADR 0007), not by these checks.

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
