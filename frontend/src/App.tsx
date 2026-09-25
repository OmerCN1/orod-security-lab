import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, GitPullRequest, Plus, RotateCcw, Shield, Square, X } from 'lucide-react'
import { getHealth, getModels, listRuns } from './api/client'
import { StatusPill } from './components/StatusPill'
import { AgentDetail } from './features/agents/AgentDetail'
import { TeamStrip } from './features/agents/TeamStrip'
import {
  agentWorkMs,
  buildRoster,
  formatDuration,
  isLive,
  selectedFindingIds,
} from './features/agents/roster'
import type { AgentId } from './features/agents/roster'
import { DecisionBar } from './features/patch/DecisionBar'
import { NewScanDialog } from './features/runs/NewScanDialog'
import { RecentRuns } from './features/runs/RecentRuns'
import { useReplay } from './features/runs/useReplay'
import { useRun } from './features/runs/useRun'
import { WorkPanel } from './panes/WorkPanel'
import type { HealthResponse, ModelOption, ReviewDecision, RunSummary } from './types'

export default function App() {
  const { run, events, error, busy, start, open, stop, review, dismissError } = useRun()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [models, setModels] = useState<ModelOption[]>([])
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [scanOpen, setScanOpen] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState<AgentId>('architect')

  const refreshHistory = useCallback(() => {
    listRuns().then(setRuns).catch(() => undefined)
  }, [])

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
    getModels().then(setModels).catch(() => setModels([]))
    refreshHistory()
  }, [refreshHistory])

  // The history list is a projection of run state, so refresh it whenever this run moves.
  useEffect(() => {
    if (run) refreshHistory()
  }, [run?.id, run?.status, refreshHistory, run])

  const live = isLive(run)
  const replay = useReplay(events, live)
  const visibleEvents = replay.events

  const roster = useMemo(
    () => buildRoster(run, visibleEvents, live || replay.playing),
    [run, visibleEvents, live, replay.playing],
  )
  const ownedFindingIds = useMemo(() => selectedFindingIds(visibleEvents), [visibleEvents])
  const selected = roster.find((snapshot) => snapshot.definition.id === selectedAgent) ?? roster[0]

  // Follow the run: the agent that is working, or the one that needs a decision.
  useEffect(() => {
    const active = roster.find(
      (snapshot) => snapshot.state === 'working' || snapshot.state === 'waiting',
    )
    if (active) setSelectedAgent(active.definition.id)
  }, [roster])

  const finished = roster.filter(
    (snapshot) => !['idle', 'working', 'waiting'].includes(snapshot.state),
  ).length
  const working = roster.find((snapshot) => snapshot.state === 'working')

  const handleStart = (target: string, model: string | null) => {
    setScanOpen(false)
    setSelectedAgent('architect')
    void start(target, model)
  }
  const handleDecide = (decision: ReviewDecision, feedback?: string) => {
    void review(decision, feedback)
  }

  return (
    <div className="flex min-h-screen flex-col" style={{ background: 'var(--pane)' }}>
      {/* --- top bar --- */}
      <header className="bar stick-top h-12 justify-between px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <Shield size={17} style={{ color: 'var(--accent)' }} />
          <b className="text-[13.5px] font-semibold tracking-[-.01em]">OROD</b>
          <span className="truncate text-[11.5px]" style={{ color: 'var(--faint)' }}>
            autonomous code security review
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3.5">
          <span
            className="mono inline-flex items-center gap-1.5 text-[11px]"
            style={{ color: health?.status === 'ok' ? 'var(--pass)' : 'var(--hold)' }}
            title={healthTitle(health)}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {health ? `all systems ${health.status}` : 'connecting'}
          </span>
          <button type="button" className="btn-primary" onClick={() => setScanOpen(true)}>
            <Plus size={13} strokeWidth={2.4} /> New scan
          </button>
        </div>
      </header>

      {error && (
        <div
          className="flex shrink-0 items-center gap-2 border-b px-4 py-2 text-[12px]"
          style={{
            borderColor: 'rgba(251,113,133,.25)',
            background: 'rgba(251,113,133,.1)',
            color: '#fecdd3',
          }}
        >
          <AlertCircle size={13} />
          <span className="min-w-0 flex-1 truncate">{error}</span>
          <button type="button" onClick={dismissError} aria-label="Dismiss error">
            <X size={13} />
          </button>
        </div>
      )}

      {/* --- run header --- */}
      {run && (
        <div className="bar flex-wrap justify-between gap-4 px-4 py-3">
          <div className="min-w-0 flex-1 basis-[300px]">
            <p className="mono truncate text-[15px] font-medium">{run.repository_url}</p>
            <p
              className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px]"
              style={{ color: 'var(--faint)' }}
            >
              <span className="mono">{run.model ?? 'server default'}</span>
              <span style={{ color: 'var(--ghost)' }}>·</span>
              <span>{run.repository?.files.length ?? 0} files</span>
              <span style={{ color: 'var(--ghost)' }}>·</span>
              <span>started {new Date(run.created_at).toLocaleTimeString([], { hour12: false })}</span>
              <span style={{ color: 'var(--ghost)' }}>·</span>
              <span className="mono">{run.id.slice(0, 8)}</span>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2.5">
            {run.pull_request && (
              <a
                className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] font-medium transition hover:brightness-110"
                style={{
                  border: '1px solid rgba(52,211,153,.32)',
                  background: 'rgba(52,211,153,.1)',
                  color: '#6ee7b7',
                }}
                href={run.pull_request.url}
                target="_blank"
                rel="noreferrer"
              >
                <GitPullRequest size={13} />
                {run.pull_request.draft ? 'Draft PR' : 'PR'}
                {run.pull_request.number !== null && ` #${run.pull_request.number}`}
              </a>
            )}
            <StatusPill status={run.status} />
            {live ? (
              <button type="button" className="btn-ghost" onClick={() => void stop()}>
                <Square size={12} fill="currentColor" /> Stop
              </button>
            ) : (
              replay.canReplay && (
                <button type="button" className="btn-ghost" onClick={replay.toggle}>
                  <RotateCcw size={13} /> {replay.playing ? 'Stop' : 'Replay run'}
                </button>
              )
            )}
          </div>
        </div>
      )}

      <RecentRuns runs={runs} activeRunId={run?.id ?? null} onSelect={(id) => void open(id)} />

      {run ? (
        <TeamStrip
          roster={roster}
          selected={selected.definition.id}
          onSelect={setSelectedAgent}
          elapsed={formatDuration(agentWorkMs(roster))}
          subtitle={
            working
              ? `${working.definition.name} is working`
              : `${finished} of ${roster.length} finished`
          }
        />
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <Shield size={26} style={{ color: 'var(--ghost)' }} />
          <p className="text-[14px] font-medium">No run open</p>
          <p className="max-w-[46ch] text-[12.5px] leading-[1.6]" style={{ color: 'var(--faint)' }}>
            Start a scan and five agents go to work: one surveys the repository, one hunts for
            vulnerabilities, one writes the fix, one checks it, and then it is your call.
          </p>
          <button type="button" className="btn-primary mt-1" onClick={() => setScanOpen(true)}>
            <Plus size={13} strokeWidth={2.4} /> New scan
          </button>
        </div>
      )}

      {run && (
        <main className="grid min-h-[560px] flex-1 grid-cols-[minmax(0,1fr)_360px]">
          <WorkPanel run={run} ownedFindingIds={ownedFindingIds} />
          <aside className="flex flex-col border-l divider" style={{ background: 'var(--ground)' }}>
            <div className="bar stick-sub h-11 px-4" style={{ background: 'var(--ground)' }}>
              <span className="label">Agent detail</span>
            </div>
            <AgentDetail snapshot={selected} />
          </aside>
        </main>
      )}

      {run?.status === 'awaiting_review' && run.review && !replay.playing && (
        <DecisionBar review={run.review} busy={busy} onDecide={handleDecide} />
      )}

      <NewScanDialog
        open={scanOpen}
        models={models}
        busy={busy}
        onStart={handleStart}
        onClose={() => setScanOpen(false)}
      />
    </div>
  )
}

function healthTitle(health: HealthResponse | null): string {
  if (!health) return 'API unreachable'
  return Object.entries(health.components)
    .map(([name, component]) => `${name}: ${component.detail}`)
    .join('\n')
}
