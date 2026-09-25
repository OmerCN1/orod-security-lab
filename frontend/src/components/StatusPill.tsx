import type { RunStatus } from '../types'

const TONE: Record<RunStatus, { border: string; background: string; color: string; dot: string }> = {
  queued: {
    border: 'var(--line-strong)',
    background: 'var(--raise)',
    color: 'var(--muted)',
    dot: 'var(--ghost)',
  },
  running: {
    border: 'rgba(79,156,249,.35)',
    background: 'rgba(79,156,249,.1)',
    color: '#93c5fd',
    dot: 'var(--busy)',
  },
  awaiting_review: {
    border: 'rgba(251,191,36,.32)',
    background: 'rgba(251,191,36,.09)',
    color: '#fcd34d',
    dot: 'var(--hold)',
  },
  completed: {
    border: 'rgba(52,211,153,.3)',
    background: 'rgba(52,211,153,.09)',
    color: '#6ee7b7',
    dot: 'var(--pass)',
  },
  failed: {
    border: 'rgba(251,113,133,.32)',
    background: 'rgba(251,113,133,.09)',
    color: '#fda4af',
    dot: 'var(--fail)',
  },
  cancelled: {
    border: 'var(--line-strong)',
    background: 'var(--raise)',
    color: 'var(--faint)',
    dot: 'var(--ghost)',
  },
}

const LABELS: Record<RunStatus, string> = {
  queued: 'queued',
  running: 'running',
  awaiting_review: 'needs review',
  completed: 'completed',
  failed: 'failed',
  cancelled: 'cancelled',
}

export function StatusPill({ status }: { status: RunStatus }) {
  const tone = TONE[status]
  return (
    <span
      className="inline-flex shrink-0 items-center gap-2 rounded-full py-1.5 pl-2.5 pr-3 text-[12px] font-medium"
      style={{ border: `1px solid ${tone.border}`, background: tone.background, color: tone.color }}
    >
      <span
        className={`h-[7px] w-[7px] shrink-0 rounded-full ${status === 'running' ? 'animate-pulse' : ''}`}
        style={{ background: tone.dot }}
      />
      {LABELS[status]}
    </span>
  )
}
