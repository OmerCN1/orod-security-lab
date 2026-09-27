import type { RunStatus, RunSummary } from '../../types'

const DOT: Record<RunStatus, string> = {
  queued: 'var(--ghost)',
  running: 'var(--busy)',
  awaiting_review: 'var(--hold)',
  completed: 'var(--pass)',
  failed: 'var(--fail)',
  cancelled: 'var(--ghost)',
}

function label(summary: RunSummary): string {
  const target = summary.owner_repo ?? summary.repository_url
  return target.replace(/^https:\/\/github\.com\//, '').replace(/^demo:\/\//, '')
}

/** Same-day runs show a clock; older ones a date. Both are cheaper to scan than a full stamp. */
function when(iso: string): string {
  const date = new Date(iso)
  const sameDay = date.toDateString() === new Date().toDateString()
  return sameDay
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    : date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function RecentRuns({
  runs,
  activeRunId,
  onSelect,
}: {
  runs: RunSummary[]
  activeRunId: string | null
  onSelect: (runId: string) => void
}) {
  if (runs.length === 0) return null

  return (
    <div
      className="flex shrink-0 items-center gap-2 overflow-x-auto border-b px-4 py-2.5 divider"
      style={{ background: 'var(--ground)' }}
    >
      <span className="label shrink-0 pr-1">Recent</span>
      {runs.map((summary) => (
        <button
          key={summary.id}
          type="button"
          onClick={() => onSelect(summary.id)}
          aria-current={summary.id === activeRunId}
          className={`chip ${summary.id === activeRunId ? 'chip-active' : ''}`}
          title={
            `${summary.total_findings} findings · ${summary.model ?? 'server default'}` +
            (summary.scan_complete === false ? ' · scan incomplete' : '')
          }
        >
          <span
            className="h-1.5 w-1.5 shrink-0 rounded-full"
            style={{ background: DOT[summary.status] }}
          />
          {label(summary)}
          {summary.scan_complete === false && (
            <span className="mono text-[10.5px]" style={{ color: 'var(--fail)' }}>
              incomplete
            </span>
          )}
          <span className="mono text-[10.5px]" style={{ color: 'var(--ghost)' }}>
            {when(summary.created_at)}
          </span>
        </button>
      ))}
    </div>
  )
}
