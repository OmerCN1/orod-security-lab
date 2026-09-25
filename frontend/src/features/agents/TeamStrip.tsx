import { AgentAvatar } from './AgentAvatar'
import { formatDuration } from './roster'
import type { AgentId, AgentSnapshot, AgentState } from './roster'

const STATE_COLOR: Record<AgentState, string> = {
  idle: 'var(--ghost)',
  working: 'var(--busy)',
  waiting: 'var(--hold)',
  done: 'var(--pass)',
  attention: 'var(--hold)',
  failed: 'var(--fail)',
}

function Seat({
  snapshot,
  selected,
  onSelect,
}: {
  snapshot: AgentSnapshot
  selected: boolean
  onSelect: () => void
}) {
  const { definition, state } = snapshot
  const color = STATE_COLOR[state]

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className="flex h-full w-full flex-col rounded-[10px] border p-3 text-left transition"
      style={{
        borderColor: selected ? 'var(--line-strong)' : 'var(--line)',
        background: selected ? 'var(--raise)' : 'var(--ground)',
      }}
    >
      <span className="flex items-center gap-2.5">
        <AgentAvatar id={definition.id} state={state} />
        <span className="min-w-0">
          <span className="block text-[13.5px] font-semibold tracking-[-.01em]">
            {definition.name}
          </span>
          <span className="label mt-px block truncate">{definition.role}</span>
        </span>
      </span>

      {/* Capped at three lines so one verbose agent cannot set the height of the whole
          strip; the full text is always in the detail panel. */}
      <p
        className="mt-3 line-clamp-3 min-h-[52px] flex-1 text-[12px] leading-[1.45]"
        style={{ color: 'var(--muted)' }}
        title={snapshot.headline}
      >
        {snapshot.headline || 'Waiting its turn.'}
      </p>

      <span className="mt-2.5 flex items-center justify-between gap-2">
        <span
          className="mono text-[10px] font-medium uppercase tracking-[.11em]"
          style={{ color }}
        >
          {snapshot.stateLabel}
        </span>
        <span className="mono num text-[11px]" style={{ color: 'var(--faint)' }}>
          {formatDuration(snapshot.durationMs)}
        </span>
      </span>

      {/* Share of the run. Reading the strip left to right shows where the time actually went. */}
      <span
        className="mt-2 block h-[3px] overflow-hidden rounded-full"
        style={{ background: 'rgba(255,255,255,.055)' }}
      >
        <span
          className="block h-full rounded-full transition-[width] duration-500"
          style={{ width: `${Math.max(snapshot.share * 100, snapshot.share > 0 ? 1.5 : 0)}%`, background: color }}
        />
      </span>

      <span
        className="mt-2.5 block h-[2px] rounded-full transition"
        style={{ background: selected ? 'var(--accent)' : 'transparent' }}
      />
    </button>
  )
}

export function TeamStrip({
  roster,
  selected,
  onSelect,
  elapsed,
  subtitle,
}: {
  roster: AgentSnapshot[]
  selected: AgentId
  onSelect: (id: AgentId) => void
  elapsed: string
  subtitle: string
}) {
  return (
    <section
      className="shrink-0 border-b px-4 pb-4 pt-3.5 divider"
      style={{
        background:
          'radial-gradient(120% 100% at 50% 0%, rgba(79,156,249,.045), transparent 62%), var(--pane)',
      }}
    >
      <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="label">The team</h2>
        <p className="text-[12px]" style={{ color: 'var(--faint)' }}>
          <b className="mono num text-[16px] font-medium" style={{ color: 'var(--text)' }}>
            {elapsed}
          </b>{' '}
          of agent work · {subtitle}
        </p>
      </div>

      <div className="grid grid-cols-[repeat(5,minmax(0,1fr))] gap-0">
        {roster.map((snapshot, index) => {
          const last = index === roster.length - 1
          const flowed = snapshot.state === 'done' || snapshot.state === 'attention'
          return (
            <div key={snapshot.definition.id} className={`relative ${last ? '' : 'pr-12'}`}>
              <Seat
                snapshot={snapshot}
                selected={selected === snapshot.definition.id}
                onSelect={() => onSelect(snapshot.definition.id)}
              />
              {!last && (
                <span
                  aria-hidden
                  className="pointer-events-none absolute right-0 top-[36px] z-10 grid w-12 place-items-center"
                >
                  <span
                    className="absolute inset-x-0.5 top-1/2 h-px"
                    style={{ background: flowed ? 'rgba(52,211,153,.4)' : 'var(--line-strong)' }}
                  />
                  <span
                    className="mono relative -top-[17px] whitespace-nowrap px-1 text-[9px] tracking-[.06em]"
                    style={{ background: 'var(--pane)', color: flowed ? 'var(--faint)' : 'var(--ghost)' }}
                  >
                    {snapshot.definition.handoff}
                  </span>
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
