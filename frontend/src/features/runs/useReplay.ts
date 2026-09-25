import { useCallback, useEffect, useRef, useState } from 'react'
import type { RunEvent } from '../../types'

const REPLAY_MS = 8000

/**
 * Replays a finished run by revealing its events again on a compressed clock.
 *
 * The whole dashboard already renders from the event list, so replay needs no parallel
 * state machine: it just hands back a prefix of that list. Every panel — the team strip,
 * the durations, the agent detail — follows for free.
 *
 * Only offered for a run that is no longer live; a live run is already doing this.
 */
export function useReplay(events: RunEvent[], live: boolean) {
  const [visibleCount, setVisibleCount] = useState<number | null>(null)
  const frameRef = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    setVisibleCount(null)
  }, [])

  // A live run, a new run, or an emptied list all end any replay in progress.
  useEffect(() => {
    if (live) stop()
  }, [live, stop])
  useEffect(() => stop, [stop])

  const start = useCallback(() => {
    if (events.length < 2) return
    const first = new Date(events[0].timestamp).getTime()
    const span = new Date(events[events.length - 1].timestamp).getTime() - first
    const startedAt = performance.now()

    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / REPLAY_MS)
      const virtualElapsed = progress * span
      const revealed = events.filter(
        (event) => new Date(event.timestamp).getTime() - first <= virtualElapsed,
      ).length
      setVisibleCount(Math.max(1, revealed))
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick)
      } else {
        frameRef.current = null
        setVisibleCount(null)
      }
    }
    frameRef.current = requestAnimationFrame(tick)
  }, [events])

  const playing = visibleCount !== null
  return {
    events: playing ? events.slice(0, visibleCount) : events,
    playing,
    canReplay: !live && events.length > 1,
    toggle: useCallback(() => (playing ? stop() : start()), [playing, start, stop]),
  }
}
