import { describe, expect, it } from 'vitest'
import type { RunEvent, RunRecord, RunStatus } from '../../types'
import {
  AGENTS,
  agentWorkMs,
  buildRoster,
  describeCommand,
  formatDuration,
  selectedFindingIds,
} from './roster'

let clock = 0

function event(partial: Partial<RunEvent>): RunEvent {
  clock += 1000
  return {
    schema_version: '1',
    event_id: `e${clock}`,
    sequence: clock / 1000,
    run_id: 'run',
    timestamp: new Date(clock).toISOString(),
    agent: 'system',
    event_type: 'run',
    level: 'info',
    message: '',
    payload: {},
    ...partial,
  }
}

function record(partial: Partial<RunRecord> = {}): RunRecord {
  return {
    id: 'run',
    repository_url: 'demo://vulnerable-python',
    base_branch: null,
    trusted: true,
    model: 'qwen2.5-coder:14b',
    status: 'running' as RunStatus,
    phase: 'developer',
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    error: null,
    repository: null,
    findings: [],
    scanners: [],
    scan_complete: null,
    patch: null,
    validation: null,
    review: null,
    pull_request: null,
    metrics: null,
    ...partial,
  }
}

const stateOf = (roster: ReturnType<typeof buildRoster>, id: string) =>
  roster.find((snapshot) => snapshot.definition.id === id)?.state

describe('buildRoster', () => {
  it('seats every agent, in pipeline order, even before a run exists', () => {
    const roster = buildRoster(null, [], false)
    expect(roster.map((snapshot) => snapshot.definition.id)).toEqual(AGENTS.map((a) => a.id))
    expect(roster.every((snapshot) => snapshot.state === 'idle')).toBe(true)
  })

  it('says nothing about an agent whose turn has not come', () => {
    // Otherwise a not-yet-started validator advertises "Compiling, linting…" from the
    // moment the run begins.
    const roster = buildRoster(
      record({ status: 'running' }),
      [event({ agent: 'architect', event_type: 'agent_started' })],
      true,
    )
    const validator = roster.find((snapshot) => snapshot.definition.id === 'validator')
    expect(validator?.state).toBe('idle')
    expect(validator?.stateLabel).toBe('not started')
    expect(validator?.headline).toBe('')
  })

  it('shows the agent holding the baton as working while the run is live', () => {
    const roster = buildRoster(
      record({ status: 'running' }),
      [
        event({ agent: 'architect', event_type: 'agent_started' }),
        event({ agent: 'architect', event_type: 'agent_completed' }),
        event({ agent: 'security', event_type: 'agent_started' }),
      ],
      true,
    )
    expect(stateOf(roster, 'architect')).toBe('done')
    expect(stateOf(roster, 'security')).toBe('working')
    expect(stateOf(roster, 'developer')).toBe('idle')
  })

  it('does not leave an agent working once the run has stopped running', () => {
    // The regression: a paused run's last developer event is an `agent_started`, because
    // the graph interrupted for review and nothing followed. Deriving state from the last
    // event left the card pulsing "working" forever while nothing was running.
    const roster = buildRoster(
      record({ status: 'awaiting_review' }),
      [
        event({ agent: 'developer', event_type: 'agent_started' }),
        event({ agent: 'developer', event_type: 'agent_completed' }),
        event({ agent: 'developer', event_type: 'agent_started' }),
      ],
      false,
    )
    expect(stateOf(roster, 'developer')).not.toBe('working')
    // It started twice, completed once and produced no patch: it failed, it is not busy.
    expect(stateOf(roster, 'developer')).toBe('failed')
  })

  it('marks the reviewer as waiting, not working, while a run is paused for a decision', () => {
    const roster = buildRoster(
      record({
        status: 'awaiting_review',
        review: {
          changed_files: ['app.py'],
          explanation: 'x',
          validation_passed: false,
          validation_summary: 'One or more validation checks failed.',
          can_approve: false,
          revision_count: 0,
          requested_at: new Date(0).toISOString(),
        },
      }),
      [event({ agent: 'reviewer', event_type: 'agent_started' })],
      false,
    )
    const reviewer = roster.find((snapshot) => snapshot.definition.id === 'reviewer')
    expect(reviewer?.state).toBe('waiting')
    expect(reviewer?.stateLabel).toBe('your turn')
    expect(reviewer?.steps.find((step) => step.label === 'Approve')?.ok).toBe(false)
  })

  it('fails the validator when validation did not pass', () => {
    const roster = buildRoster(
      record({
        status: 'awaiting_review',
        validation: {
          passed: false,
          summary: 'One or more validation checks failed.',
          new_high_findings: 0,
          tolerated_failures: 0,
          tests_ran: null,
          commands: [
            { argv: ['/venv/bin/python', '-m', 'compileall', '-q', '.'], return_code: 0, duration_ms: 26 },
            { argv: ['/venv/bin/python', '-m', 'pytest', '-q'], return_code: 1, duration_ms: 482 },
          ],
        },
      }),
      [
        event({ agent: 'validator', event_type: 'agent_started' }),
        event({ agent: 'validator', event_type: 'agent_completed', level: 'warning' }),
      ],
      false,
    )
    const validator = roster.find((snapshot) => snapshot.definition.id === 'validator')
    expect(validator?.state).toBe('failed')
    expect(validator?.stateLabel).toBe('blocked')
    expect(validator?.steps.map((step) => step.ok)).toEqual([true, false])
    expect(validator?.verdict?.tone).toBe('bad')
  })

  it('does not call a scan clean when a scanner failed', () => {
    const roster = buildRoster(
      record({ status: 'completed', scan_complete: false }),
      [
        event({ agent: 'security', event_type: 'agent_started' }),
        event({ agent: 'security', payload: { scanner: 'builtin-python', count: 0, ok: true } }),
        event({
          agent: 'security',
          level: 'warning',
          payload: { scanner: 'bandit', count: 0, ok: false, error: 'ScannerOutputError' },
        }),
        event({ agent: 'security', event_type: 'agent_completed', level: 'warning' }),
      ],
      false,
    )
    const security = roster.find((snapshot) => snapshot.definition.id === 'security')
    expect(security?.state).toBe('attention')
    expect(security?.stateLabel).toBe('incomplete')
    expect(security?.headline).toContain('bandit failed')
    expect(security?.headline).toContain('not the same as clean')
    expect(security?.steps.map((step) => [step.label, step.ok])).toEqual([
      ['builtin-python', true],
      ['bandit', false],
    ])
    expect(security?.verdict?.tone).toBe('bad')
  })

  it('reports a scan in which every scanner failed as failed', () => {
    const roster = buildRoster(
      record({ status: 'failed', scan_complete: false }),
      [
        event({ agent: 'security', event_type: 'agent_started' }),
        event({ agent: 'security', level: 'warning', payload: { scanner: 'bandit', ok: false } }),
        event({ agent: 'security', event_type: 'agent_completed', level: 'error' }),
      ],
      false,
    )
    const security = roster.find((snapshot) => snapshot.definition.id === 'security')
    expect(security?.state).toBe('failed')
    expect(security?.stateLabel).toBe('scan failed')
    expect(security?.verdict?.title).toBe('No scanner completed')
  })

  it('ignores the run record for an agent that has not finished in the visible stream', () => {
    // Replay hands back a prefix of the events while the run record stays final. An agent
    // still in flight must report what is known so far, not the eventual answer.
    const roster = buildRoster(
      record({
        status: 'awaiting_review',
        validation: {
          passed: false,
          summary: 'failed',
          new_high_findings: 0,
          tolerated_failures: 0,
          tests_ran: null,
          commands: [],
        },
      }),
      [event({ agent: 'validator', event_type: 'agent_started' })],
      true,
    )
    const validator = roster.find((snapshot) => snapshot.definition.id === 'validator')
    expect(validator?.state).toBe('working')
    expect(validator?.stateLabel).toBe('checking')
    expect(validator?.verdict).toBeNull()
  })

  it('reports the developer as needing attention when a diff was rejected on the way', () => {
    const roster = buildRoster(
      record({
        status: 'awaiting_review',
        patch: {
          unified_diff: '',
          changed_files: ['app.py'],
          finding_ids: [],
          explanation: 'x',
          validation_commands: [],
        },
      }),
      [
        event({ agent: 'developer', event_type: 'agent_started' }),
        event({
          agent: 'developer',
          event_type: 'patch',
          level: 'warning',
          payload: { attempt: 1, reason: 'corrupt patch at line 10' },
        }),
        event({ agent: 'developer', event_type: 'patch', payload: { attempt: 2, changed_files: ['app.py'] } }),
        event({ agent: 'developer', event_type: 'agent_completed' }),
      ],
      false,
    )
    const developer = roster.find((snapshot) => snapshot.definition.id === 'developer')
    expect(developer?.state).toBe('attention')
    expect(developer?.headline).toContain('would not apply')
    expect(developer?.steps.map((step) => step.ok)).toEqual([false, true])
  })

  it('gives each agent a share of the run so the strip shows where the time went', () => {
    clock = 0
    const events = [
      event({ agent: 'architect', event_type: 'agent_started' }),
      event({ agent: 'architect', event_type: 'agent_completed' }),
      event({ agent: 'developer', event_type: 'agent_started' }),
      // the developer holds the baton for the rest of the run
      { ...event({ agent: 'developer', event_type: 'agent_completed' }), timestamp: new Date(11_000).toISOString() },
    ]
    // The architect holds 1s of agent work and the developer 8s, so the shares are
    // ninths: they divide the work, not the wall clock.
    const roster = buildRoster(record({ status: 'completed' }), events, false)
    const share = (id: string) => roster.find((s) => s.definition.id === id)?.share ?? 0
    expect(share('architect')).toBeCloseTo(1 / 9, 3)
    expect(share('developer')).toBeCloseTo(8 / 9, 3)
    expect(share('architect') + share('developer')).toBeCloseTo(1, 5)
    expect(agentWorkMs(roster)).toBe(9000)
  })

  it('does not let time spent waiting on a person count as agent work', () => {
    // A reviewer took 16 minutes to decide on one real run. Counting that as work made
    // every machine bar a sliver and hid what the strip exists to show.
    clock = 0
    const events = [
      event({ agent: 'developer', event_type: 'agent_started' }),
      { ...event({ agent: 'developer', event_type: 'agent_completed' }), timestamp: new Date(9_000).toISOString() },
      { ...event({ agent: 'reviewer', event_type: 'agent_started' }), timestamp: new Date(9_000).toISOString() },
      { ...event({ agent: 'reviewer', event_type: 'agent_completed' }), timestamp: new Date(969_000).toISOString() },
    ]
    const roster = buildRoster(record({ status: 'completed' }), events, false)
    const seat = (id: string) => roster.find((s) => s.definition.id === id)!

    expect(agentWorkMs(roster)).toBe(8000)
    expect(seat('developer').share).toBe(1)
    // The wait is still reported, it just does not compete for the bar.
    expect(seat('reviewer').share).toBe(0)
    expect(seat('reviewer').durationMs).toBe(960_000)
    expect(formatDuration(seat('reviewer').durationMs)).toBe('16m 0s')
  })
})

describe('selectedFindingIds', () => {
  it('reads the findings the security agent handed to the developer', () => {
    const ids = selectedFindingIds([
      event({ agent: 'security', payload: { selected_count: 2, selected_finding_ids: ['a', 'b'] } }),
    ])
    expect([...ids]).toEqual(['a', 'b'])
  })

  it('is empty when triage has not happened yet', () => {
    expect(selectedFindingIds([]).size).toBe(0)
  })
})

describe('describeCommand', () => {
  it('reduces a python -m invocation to the tool being run', () => {
    expect(describeCommand(['/long/path/.venv/bin/python', '-m', 'pytest', '-q'])).toBe('pytest -q')
  })

  it('keeps a plain executable but drops its directory', () => {
    expect(describeCommand(['/usr/bin/git', 'apply', '--check'])).toBe('git apply --check')
  })
})
