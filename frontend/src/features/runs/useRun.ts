import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelRun, createRun, getRun, submitReview, subscribeToRun } from '../../api/client'
import type { ReviewDecision, RunEvent, RunRecord, RunStatus } from '../../types'
import { TERMINAL_STATUSES } from '../../types'

interface UseRun {
  run: RunRecord | null
  events: RunEvent[]
  error: string | null
  busy: boolean
  start: (repositoryUrl: string, model: string | null) => Promise<void>
  open: (runId: string) => Promise<void>
  stop: () => Promise<void>
  review: (decision: ReviewDecision, feedback?: string) => Promise<void>
  dismissError: () => void
}

const isTerminal = (status: RunStatus | null | undefined): boolean =>
  status != null && TERMINAL_STATUSES.includes(status)

/**
 * Owns the lifecycle of one run: the record, its event stream, and the SSE connection.
 *
 * The stream doubles as the history: the backend replays every persisted event from the
 * cursor before streaming new ones, so opening a finished run from the history list uses
 * exactly the same path as watching a live one. A run paused for review is deliberately
 * not treated as finished — the connection stays open so the decision and everything
 * after it arrive on the same stream.
 */
export function useRun(): UseRun {
  const [run, setRun] = useState<RunRecord | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const sourceRef = useRef<EventSource | null>(null)
  const cursorRef = useRef(0)
  const runIdRef = useRef<string | null>(null)
  const statusRef = useRef<RunStatus | null>(null)

  const closeStream = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  useEffect(() => closeStream, [closeStream])

  const refresh = useCallback(async (runId: string) => {
    const current = await getRun(runId)
    if (runIdRef.current !== runId) return
    statusRef.current = current.status
    setRun(current)
  }, [])

  const connect = useCallback(
    (runId: string) => {
      closeStream()
      sourceRef.current = subscribeToRun(
        runId,
        (event) => {
          if (runIdRef.current !== runId) return
          cursorRef.current = Math.max(cursorRef.current, event.sequence)
          setEvents((current) =>
            current.some((item) => item.event_id === event.event_id)
              ? current
              : [...current, event],
          )
          void refresh(runId).catch(() => undefined)
        },
        () => {
          // The server ends the stream once the run is terminal. Without this the browser
          // would reconnect forever to a stream that has nothing left to send.
          if (isTerminal(statusRef.current)) {
            closeStream()
            return
          }
          void refresh(runId).catch(() => undefined)
        },
        cursorRef.current,
      )
    },
    [closeStream, refresh],
  )

  const guard = useCallback(async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }, [])

  const attach = useCallback(
    (record: RunRecord) => {
      runIdRef.current = record.id
      statusRef.current = record.status
      cursorRef.current = 0
      setRun(record)
      setEvents([])
      connect(record.id)
    },
    [connect],
  )

  const start = useCallback(
    (repositoryUrl: string, model: string | null) =>
      guard(async () => attach(await createRun(repositoryUrl.trim(), model))),
    [attach, guard],
  )

  const open = useCallback(
    (runId: string) => guard(async () => attach(await getRun(runId))),
    [attach, guard],
  )

  const stop = useCallback(
    () =>
      guard(async () => {
        const runId = runIdRef.current
        if (!runId) return
        closeStream()
        const cancelled = await cancelRun(runId)
        statusRef.current = cancelled.status
        setRun(cancelled)
      }),
    [closeStream, guard],
  )

  const review = useCallback(
    (decision: ReviewDecision, feedback?: string) =>
      guard(async () => {
        const runId = runIdRef.current
        if (!runId) return
        const updated = await submitReview(runId, decision, feedback)
        statusRef.current = updated.status
        setRun(updated)
        if (!sourceRef.current) connect(runId)
      }),
    [connect, guard],
  )

  return {
    run,
    events,
    error,
    busy,
    start,
    open,
    stop,
    review,
    dismissError: useCallback(() => setError(null), []),
  }
}
