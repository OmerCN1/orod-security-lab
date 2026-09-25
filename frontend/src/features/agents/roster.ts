import type { RunEvent, RunRecord } from '../../types'

export type AgentId = 'architect' | 'security' | 'developer' | 'validator' | 'reviewer'

/** `working` is reserved for a run that is actually live — see `resolveState`. */
export type AgentState = 'idle' | 'working' | 'done' | 'attention' | 'failed' | 'waiting'

export interface AgentDefinition {
  id: AgentId
  name: string
  /** Two words under the name, in the present tense: what this agent is for. */
  role: string
  /** One sentence for the detail panel. */
  purpose: string
  /** What it hands to the next agent, written on the connector. */
  handoff: string
}

export interface AgentStep {
  /** `null` renders as a neutral bullet — a step that neither passed nor failed. */
  ok: boolean | null
  label: string
  detail?: string
  meta?: string
  /** Marks a step that went out to the language model, which is worth seeing. */
  model?: boolean
}

export interface AgentSnapshot {
  definition: AgentDefinition
  state: AgentState
  /** Short status under the card, e.g. `4 findings`, `blocked`. */
  stateLabel: string
  /** A plain sentence about what this agent actually did, built from run data. */
  headline: string
  steps: AgentStep[]
  /** Set when the outcome needs a call-out below the steps. */
  verdict: { tone: 'bad' | 'wait'; title: string; detail: string } | null
  durationMs: number | null
  /** Share of the run's total span, 0–1. Drives the bar under each card. */
  share: number
  events: RunEvent[]
}

export const AGENTS: readonly AgentDefinition[] = [
  {
    id: 'architect',
    name: 'Architect',
    role: 'surveys',
    purpose: 'Works out what kind of repository this is',
    handoff: 'files',
  },
  {
    id: 'security',
    name: 'Security',
    role: 'investigates',
    purpose: 'Runs every scanner and merges what they find',
    handoff: 'findings',
  },
  {
    id: 'developer',
    name: 'Developer',
    role: 'writes the fix',
    purpose: 'Writes the patch and applies it',
    handoff: 'patch',
  },
  {
    id: 'validator',
    name: 'Validator',
    role: 'checks the work',
    purpose: 'Decides whether the patch is safe to ship',
    handoff: 'verdict',
  },
  {
    id: 'reviewer',
    name: 'Reviewer',
    role: 'that is you',
    purpose: 'That is you — the graph pauses here',
    handoff: '',
  },
]

const LIVE_STATUSES = new Set(['queued', 'running'])

/**
 * What the visible event stream says about one agent's lifecycle.
 *
 * Everything downstream keys off `finished`. An agent that has started and not yet
 * completed has no trustworthy output, so its card must not borrow the run record's
 * final answer — that is what makes both live runs and replays honest.
 */
interface Lifecycle {
  started: number
  completed: number
  pending: boolean
  finished: boolean
}

function lifecycleOf(events: RunEvent[], live: boolean): Lifecycle {
  const started = events.filter((event) => event.event_type === 'agent_started').length
  const completed = events.filter((event) => event.event_type === 'agent_completed').length
  const pending = started > completed
  // `started > completed` is normal even for a finished agent: the developer announces
  // every attempt but only completes a successful one. So once the run is no longer
  // live - nothing is in flight - any agent that reported a completion has finished.
  return { started, completed, pending, finished: completed > 0 && (!pending || !live) }
}

function num(payload: Record<string, unknown>, key: string): number | null {
  const value = payload[key]
  return typeof value === 'number' ? value : null
}

function str(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key]
  return typeof value === 'string' ? value : null
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

interface Context {
  run: RunRecord
  events: RunEvent[]
  life: Lifecycle
  live: boolean
}

/**
 * Derives one agent's state.
 *
 * Deriving it from the last event alone is what used to leave the developer pulsing
 * forever: its final event is an `agent_started`, because the run then paused for review
 * and nothing followed. So a pending agent is only ever `working` while the run is live;
 * otherwise it is called out as needing attention.
 */
function resolveState({ run, events, life, live }: Context, id: AgentId): AgentState {
  if (events.length === 0) return 'idle'

  if (id === 'reviewer') {
    if (life.pending) return run.status === 'awaiting_review' ? 'waiting' : 'working'
    return run.metrics?.review_decision === 'reject' ? 'attention' : 'done'
  }

  if (life.pending && live) return 'working'

  if (id === 'validator' && life.finished && run.validation) {
    return run.validation.passed ? 'done' : 'failed'
  }
  if (id === 'developer' && life.finished) {
    if (!run.patch) return 'failed'
    if (events.some((event) => event.event_type === 'patch' && event.level === 'warning')) {
      return 'attention'
    }
  }
  // Started, never completed, and nothing is running: say so rather than showing it busy.
  if (life.pending) return 'attention'
  if (events.some((event) => event.level === 'error')) return 'failed'
  if (events.some((event) => event.level === 'warning')) return 'attention'
  return 'done'
}

function architect({ run, events, life }: Context): Partial<AgentSnapshot> {
  if (!life.finished) {
    return { stateLabel: 'reading', headline: 'Opening the repository and reading every file…' }
  }
  const done = events.find((event) => event.event_type === 'agent_completed')
  const files = run.repository?.files ?? []
  return {
    stateLabel: 'mapped',
    headline: run.repository?.summary ?? done?.message ?? '',
    steps: files.map((file) => ({
      ok: null,
      label: file.path,
      detail: `${file.size} bytes${file.language ? ` · ${file.language}` : ''}`,
    })),
  }
}

function security({ events, life }: Context): Partial<AgentSnapshot> {
  // Counted from the visible stream rather than run.findings, so a partially revealed
  // run reports what is actually known at that point.
  const found = events.filter((event) => event.event_type === 'finding')
  const high = found.filter((event) => {
    const severity = str(event.payload, 'severity')
    return severity === 'high' || severity === 'critical'
  }).length

  const steps: AgentStep[] = events
    .filter((event) => str(event.payload, 'scanner') !== null)
    .map((event) => {
      const count = num(event.payload, 'count') ?? 0
      return {
        ok: true,
        label: str(event.payload, 'scanner') ?? 'scanner',
        detail: count === 0 ? 'clean' : plural(count, 'finding'),
      }
    })

  const triage = events.find((event) => num(event.payload, 'selected_count') !== null)
  const selected = triage ? num(triage.payload, 'selected_count') : null
  const manual = triage ? num(triage.payload, 'review_only_count') : null

  if (!life.finished) {
    return {
      stateLabel: steps.length > 0 ? `${steps.length} of 4` : 'scanning',
      headline:
        steps.length > 0
          ? `Ran ${plural(steps.length, 'scanner')} so far…`
          : 'Running bandit, semgrep, osv and the built-in pass…',
      steps,
    }
  }

  return {
    stateLabel: found.length > 0 ? plural(found.length, 'finding') : 'all clear',
    headline:
      found.length === 0
        ? `Ran ${plural(steps.length, 'scanner')} and found nothing to fix.`
        : `Ran ${plural(steps.length, 'scanner')}. Found ${plural(found.length, 'problem')}` +
          (high > 0 ? ` — ${high} of them high severity.` : '.'),
    steps,
    verdict:
      selected === null
        ? null
        : {
            tone: 'wait',
            title: `Handed on: ${plural(selected, 'finding')} to the Developer`,
            detail:
              manual && manual > 0
                ? `${manual} kept back for you — there is no safe automatic rewrite for ${manual === 1 ? 'it' : 'them'}.`
                : 'Nothing needed a human.',
          },
  }
}

function developer({ run, events, life }: Context): Partial<AgentSnapshot> {
  const attempts = events.filter((event) => event.event_type === 'patch')
  const steps: AgentStep[] = attempts.map((event) => {
    const attempt = num(event.payload, 'attempt')
    const reason = str(event.payload, 'reason')
    const label = `attempt ${attempt ?? '?'}${run.model ? ` · ${run.model}` : ''}`
    return reason === null
      ? { ok: true, label, detail: event.message, model: true }
      : { ok: false, label, detail: `rejected — ${reason}`, model: true }
  })

  if (!life.finished) {
    const current = attempts.length + 1
    return {
      stateLabel: 'thinking',
      headline:
        attempts.length === 0
          ? `Attempt 1 — asking ${run.model ?? 'the model'} for a patch…`
          : `Attempt ${current} — the previous diff would not apply, trying again…`,
      steps,
    }
  }

  const rejected = attempts.filter((event) => str(event.payload, 'reason') !== null).length
  let headline = 'No patch was needed.'
  if (run.patch) {
    headline =
      rejected > 0
        ? `Took ${plural(attempts.length, 'attempt')} — ${rejected} came back as a diff that would not apply. Patched ${plural(run.patch.changed_files.length, 'file')}.`
        : `Patched ${plural(run.patch.changed_files.length, 'file')} first time.`
  } else if (attempts.length > 0) {
    headline = `Tried ${plural(attempts.length, 'time')}. No usable patch came back.`
  }

  return {
    stateLabel: attempts.length > 1 ? plural(attempts.length, 'attempt') : 'patched',
    headline,
    steps,
    verdict:
      run.patch === null && attempts.length > 0
        ? {
            tone: 'bad',
            title: 'No patch was applied.',
            detail: 'Every attempt produced a diff git apply refused, so nothing was changed.',
          }
        : null,
  }
}

function validator({ run, life }: Context): Partial<AgentSnapshot> {
  if (!life.finished || !run.validation) {
    return {
      stateLabel: 'checking',
      headline: 'Compiling, linting, re-scanning and running the tests…',
    }
  }
  const commands = run.validation.commands
  const failed = commands.filter((command) => command.return_code !== 0).length
  return {
    stateLabel: run.validation.passed ? 'all clear' : 'blocked',
    headline: run.validation.passed
      ? `All ${plural(commands.length, 'check')} passed. The patch is safe to ship.`
      : `Ran ${plural(commands.length, 'gate')}. ${failed} failed.`,
    steps: commands.map((command) => ({
      ok: command.return_code === 0,
      label: describeCommand(command.argv),
      meta: `${command.duration_ms}ms`,
    })),
    verdict: run.validation.passed
      ? null
      : {
          tone: 'bad',
          title: 'Blocked.',
          detail: `${run.validation.summary} This gate is enforced in the graph and again in the API, so no request path can push a failing patch.`,
        },
  }
}

function reviewer({ run, life }: Context): Partial<AgentSnapshot> {
  if (life.pending && run.status === 'awaiting_review' && run.review) {
    return {
      stateLabel: 'your turn',
      headline: 'Everything is parked until you decide. Nothing is pushed, nothing is lost.',
      steps: [
        {
          ok: run.review.can_approve,
          label: 'Approve',
          detail: run.review.can_approve
            ? 'opens a draft pull request'
            : 'locked — validation did not pass',
        },
        { ok: null, label: 'Send it back', detail: 'your note goes to the Developer, it tries again' },
        { ok: null, label: 'Reject', detail: 'closes the run and keeps the findings' },
      ],
      verdict: {
        tone: 'wait',
        title: 'Waiting for you.',
        detail:
          'The run stopped at a real interrupt in the pipeline. Its checkpoint is on disk, so this survives a backend restart.',
      },
    }
  }
  const decision = run.metrics?.review_decision ?? null
  return {
    stateLabel: decision ?? 'not reached',
    headline: decision
      ? `You chose to ${decision} this patch.`
      : 'Everything is parked until you decide.',
    steps: [],
  }
}

/** Turns a validation argv into something readable: `python -m pytest -q` → `pytest -q`. */
export function describeCommand(argv: string[]): string {
  const moduleIndex = argv.indexOf('-m')
  if (moduleIndex >= 0 && argv[moduleIndex + 1]) return argv.slice(moduleIndex + 1).join(' ')
  const [head, ...rest] = argv
  return [head?.split('/').pop() ?? '', ...rest].join(' ').trim()
}

const BUILDERS: Record<AgentId, (context: Context) => Partial<AgentSnapshot>> = {
  architect,
  security,
  developer,
  validator,
  reviewer,
}

const EMPTY: Omit<AgentSnapshot, 'definition'> = {
  state: 'idle',
  stateLabel: 'not started',
  headline: '',
  steps: [],
  verdict: null,
  durationMs: null,
  share: 0,
  events: [],
}

/**
 * Builds the full roster for one run.
 *
 * Every sentence is derived from the run record or an event payload — nothing is
 * hard-coded per repository, so the strip reads the same for a demo fixture and a real
 * GitHub scan.
 *
 * `live` is passed in rather than read off the run so a replay can borrow it: replaying
 * a finished run is, for display purposes, exactly a live run with fewer events so far.
 */
export function buildRoster(
  run: RunRecord | null,
  events: RunEvent[],
  live: boolean,
): AgentSnapshot[] {
  // The denominator is agent *work*, not wall-clock. The reviewer's span is a person
  // thinking - it was 16 minutes on one real run - and counting it turns every machine
  // bar into a sliver, hiding the thing the strip exists to show.
  const durations = new Map<AgentId, number | null>(
    AGENTS.map((definition) => [
      definition.id,
      agentSpanMs(events.filter((event) => event.agent === definition.id)),
    ]),
  )
  const workMs = AGENTS.reduce(
    (total, definition) =>
      definition.id === 'reviewer' ? total : total + (durations.get(definition.id) ?? 0),
    0,
  )

  return AGENTS.map((definition) => {
    if (run === null) return { definition, ...EMPTY }
    const mine = events.filter((event) => event.agent === definition.id)
    // An agent with no events has not been reached. Without this the builders would
    // report their in-progress narrative ("Compiling, linting…") for an agent whose turn
    // has not come, which is exactly what a replay makes visible.
    if (mine.length === 0) return { definition, ...EMPTY }
    const context: Context = { run, events: mine, life: lifecycleOf(mine, live), live }
    const built = BUILDERS[definition.id](context)
    const durationMs = durations.get(definition.id) ?? null
    const counts = definition.id !== 'reviewer' && durationMs !== null && workMs > 0
    return {
      definition,
      ...EMPTY,
      ...built,
      state: resolveState(context, definition.id),
      durationMs,
      share: counts ? Math.min(1, durationMs / workMs) : 0,
      events: mine,
    }
  })
}

/** Total time the agents spent working, excluding any wait on a human decision. */
export function agentWorkMs(roster: AgentSnapshot[]): number {
  return roster.reduce(
    (total, snapshot) =>
      snapshot.definition.id === 'reviewer' ? total : total + (snapshot.durationMs ?? 0),
    0,
  )
}

/** True when the run itself is still executing, as opposed to paused or finished. */
export function isLive(run: RunRecord | null): boolean {
  return run !== null && LIVE_STATUSES.has(run.status)
}

/** The findings the Security agent handed to the Developer, from its triage event. */
export function selectedFindingIds(events: RunEvent[]): Set<string> {
  const triage = events.find((event) => Array.isArray(event.payload.selected_finding_ids))
  const ids = triage?.payload.selected_finding_ids
  return new Set(Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [])
}

function at(event: RunEvent): number {
  return new Date(event.timestamp).getTime()
}

export function totalSpanMs(events: RunEvent[]): number {
  if (events.length < 2) return 0
  return Math.max(0, at(events[events.length - 1]) - at(events[0]))
}

/**
 * How long this agent held the baton, measured from its first to its last event. An
 * agent with a single event has no measurable span, which is honest: the work took less
 * time than the clock can see.
 */
function agentSpanMs(events: RunEvent[]): number | null {
  if (events.length === 0) return null
  return Math.max(0, at(events[events.length - 1]) - at(events[0]))
}

export function formatDuration(ms: number | null): string {
  if (ms === null || ms === 0) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`
  const minutes = Math.floor(ms / 60_000)
  return `${minutes}m ${Math.round((ms % 60_000) / 1000)}s`
}
