import { useEffect, useState } from 'react'
import { Check, ChevronRight, Circle, X } from 'lucide-react'
import { AgentAvatar } from './AgentAvatar'
import { formatDuration } from './roster'
import type { AgentSnapshot, AgentStep } from './roster'
import type { RunEvent } from '../../types'

function StepRow({ step }: { step: AgentStep }) {
  const icon =
    step.ok === null ? (
      <Circle size={7} style={{ color: 'var(--ghost)' }} fill="currentColor" />
    ) : step.ok ? (
      <Check size={13} strokeWidth={2.6} style={{ color: 'var(--pass)' }} />
    ) : (
      <X size={13} strokeWidth={2.6} style={{ color: 'var(--fail)' }} />
    )

  return (
    <div
      className="grid grid-cols-[15px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-md px-2.5 py-2 text-[12px]"
      style={{ background: step.model ? 'rgba(167,139,250,.09)' : 'var(--pane)', color: 'var(--muted)' }}
    >
      <span className="grid place-items-center">{icon}</span>
      <span className="min-w-0">
        <span className="mono block truncate text-[11.5px]" style={{ color: 'var(--text)' }}>
          {step.label}
        </span>
        {step.detail && (
          <span className="mt-0.5 block text-[11px] leading-[1.45]" style={{ color: 'var(--faint)' }}>
            {step.detail}
          </span>
        )}
      </span>
      <span
        className="mono num text-[10.5px]"
        style={{ color: step.model ? 'var(--id-developer)' : 'var(--ghost)' }}
      >
        {step.meta ?? ''}
      </span>
    </div>
  )
}

function timeOf(event: RunEvent): string {
  return new Date(event.timestamp).toLocaleTimeString([], { hour12: false })
}

export function AgentDetail({ snapshot }: { snapshot: AgentSnapshot }) {
  const [rawOpen, setRawOpen] = useState(false)
  const { definition } = snapshot

  // A different agent is a different story; collapse the raw log again when it changes.
  useEffect(() => setRawOpen(false), [definition.id])

  return (
    <div className="p-4">
      <div className="flex items-center gap-3">
        <AgentAvatar id={definition.id} state={snapshot.state} size={38} />
        <div className="min-w-0">
          <p className="text-[15px] font-semibold tracking-[-.015em]">{definition.name}</p>
          <p className="mt-0.5 text-[12px]" style={{ color: 'var(--faint)' }}>
            {definition.purpose}
          </p>
        </div>
        <span className="mono num ml-auto text-[11px]" style={{ color: 'var(--faint)' }}>
          {formatDuration(snapshot.durationMs)}
        </span>
      </div>

      {snapshot.headline && (
        <p
          className="mt-3.5 rounded-lg px-3 py-2.5 text-[12.5px] leading-[1.6]"
          style={{ background: 'var(--raise)', color: 'var(--muted)' }}
        >
          {snapshot.headline}
        </p>
      )}

      {snapshot.steps.length > 0 && (
        <div className="mt-3.5 flex flex-col gap-1">
          {snapshot.steps.map((step, index) => (
            <StepRow key={`${step.label}-${index}`} step={step} />
          ))}
        </div>
      )}

      {snapshot.verdict && (
        <div
          className="mt-3 rounded-lg px-3 py-2.5 text-[12.5px] leading-[1.55]"
          style={
            snapshot.verdict.tone === 'bad'
              ? {
                  border: '1px solid rgba(251,113,133,.28)',
                  background: 'rgba(251,113,133,.07)',
                  color: '#fecdd3',
                }
              : {
                  border: '1px solid rgba(251,191,36,.28)',
                  background: 'rgba(251,191,36,.07)',
                  color: '#fde68a',
                }
          }
        >
          <b className="font-semibold">{snapshot.verdict.title}</b>
          <span className="mt-1 block" style={{ color: 'var(--muted)' }}>
            {snapshot.verdict.detail}
          </span>
        </div>
      )}

      {snapshot.events.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setRawOpen((open) => !open)}
            aria-expanded={rawOpen}
            className="mono mt-3.5 inline-flex items-center gap-2 text-[10.5px] transition"
            style={{ color: 'var(--ghost)' }}
          >
            <ChevronRight
              size={10}
              strokeWidth={2.5}
              className="transition-transform"
              style={{ transform: rawOpen ? 'rotate(90deg)' : undefined }}
            />
            {snapshot.events.length} raw event{snapshot.events.length === 1 ? '' : 's'}
          </button>
          {rawOpen && (
            <div className="mt-2 flex flex-col gap-1 border-l pl-3 divider">
              {snapshot.events.map((event) => (
                <div
                  key={event.event_id}
                  className="mono grid grid-cols-[62px_minmax(0,1fr)] gap-2.5 text-[10.5px] leading-[1.55]"
                  style={{ color: 'var(--faint)' }}
                >
                  <span className="num" style={{ color: 'var(--ghost)' }}>
                    {timeOf(event)}
                  </span>
                  <span
                    className="min-w-0 break-words"
                    style={{
                      color:
                        event.level === 'error'
                          ? 'var(--fail)'
                          : event.level === 'warning'
                            ? 'var(--hold)'
                            : undefined,
                    }}
                  >
                    {event.event_type} · {event.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {snapshot.events.length === 0 && snapshot.steps.length === 0 && (
        <p className="mt-4 text-[12px]" style={{ color: 'var(--faint)' }}>
          This agent has not been reached yet.
        </p>
      )}
    </div>
  )
}
