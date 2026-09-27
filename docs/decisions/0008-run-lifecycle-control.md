# ADR 0008: Run lifecycle control in the coordinator

## Context

`RunCoordinator` checked a run and then acted on it with awaits in between. Two review
decisions arriving together both passed the checks and resumed the graph twice. The
review node marks a run `awaiting_review` just before it interrupts, so a quick decision
could also meet the still-living pausing task and be refused as "already being applied".
`cancel` overwrote completed and failed runs, and saved `cancelled` without waiting for
the task, whose subprocesses and containers could still be running. Any number of runs
could execute at once. After a restart, runs left `running` stayed that way forever and
their event streams polled indefinitely.

## Decision

Every check-then-act decision (resume a review, cancel) runs under one coordinator lock
that is held only for store access and task bookkeeping, never while a run executes.

A decision is tied to the review round it answers (`ReviewRequest.requested_at`). A
second decision for an answered round is refused; a task that is still pausing a newer
round is awaited briefly, then the decision is applied.

`cancel` never rewrites a completed or failed run (HTTP 409) and is idempotent for a
cancelled one. It cancels an executing task, waits up to `cancel_grace_seconds` for its
cleanup, and keeps the run's result if it finished before the cancellation landed.

A semaphore bounds executing runs at `max_concurrent_runs`; resumed reviews take a slot.

At startup, runs left `queued` or `running` are marked `failed` with an "interrupted"
error. They are not resumed from their checkpoints: nodes before the review are not
idempotent (preparing a workspace, applying a patch), and a clear failure is safer than a
partial replay. Runs `awaiting_review` stay resumable.

## Consequences

The coordinator assumes one backend process owns the database; several workers would
need database-level claims instead of an in-process lock. Queued runs are held in memory
and do not survive a restart; they are failed like running ones. A run whose cleanup
exceeds the grace period is still recorded as cancelled, with a warning event saying so.
