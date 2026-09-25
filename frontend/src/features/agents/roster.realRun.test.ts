import { describe, expect, it } from 'vitest'
import fixture from './__fixtures__/paused-run.json'
import type { RunEvent, RunRecord } from '../../types'
import { buildRoster, formatDuration, selectedFindingIds, totalSpanMs } from './roster'

/**
 * The strip read against a real recorded run rather than hand-built events.
 *
 * `paused-run.json` is the verbatim API output of a `demo://vulnerable-python` scan with
 * `qwen2.5-coder:14b`, trimmed only of command stdout. It pins the whole narrative
 * pipeline — event attribution, lifecycle, sentences — to what the backend actually
 * emits, so a change on either side that breaks the story fails here.
 */
const run = fixture.run as unknown as RunRecord
const events = fixture.events as unknown as RunEvent[]

const roster = buildRoster(run, events, false)
const seat = (id: string) => roster.find((snapshot) => snapshot.definition.id === id)!

describe('the strip, against a real paused run', () => {
  it('is the run this fixture claims to be', () => {
    expect(run.status).toBe('awaiting_review')
    expect(run.validation?.passed).toBe(false)
    expect(run.findings).toHaveLength(4)
  })

  it('gives every agent a state, and none of them is stuck working', () => {
    expect(roster.map((snapshot) => snapshot.state)).toEqual([
      'done', // architect
      'done', // security
      'attention', // developer — one attempt produced a diff that would not apply
      'failed', // validator — two of four gates failed
      'waiting', // reviewer — the graph is paused here
    ])
  })

  it('says what the architect learned', () => {
    expect(seat('architect').headline).toContain('Python repository')
    expect(seat('architect').steps.map((step) => step.label)).toContain('app.py')
  })

  it('names every scanner the security agent ran', () => {
    expect(seat('security').steps.map((step) => step.label)).toEqual([
      'builtin-python',
      'bandit',
      'semgrep',
      'osv',
    ])
    expect(seat('security').headline).toContain('4 problems')
    expect(seat('security').verdict?.title).toContain('3 findings to the Developer')
  })

  it('reports the developer as two attempts, the first rejected', () => {
    const developer = seat('developer')
    expect(developer.steps.map((step) => step.ok)).toEqual([false, true])
    expect(developer.steps[0].detail).toContain('corrupt patch')
    expect(developer.steps.every((step) => step.model)).toBe(true)
    expect(developer.headline).toContain('would not apply')
  })

  it('shows which validation gates failed', () => {
    const validator = seat('validator')
    const failed = validator.steps.filter((step) => step.ok === false).map((step) => step.label)
    expect(failed).toEqual(['bandit -r . -f json -lll', 'pytest -q'])
    expect(validator.verdict?.tone).toBe('bad')
  })

  it('locks the reviewer out of approving, because validation failed', () => {
    const reviewer = seat('reviewer')
    expect(reviewer.state).toBe('waiting')
    expect(reviewer.steps.find((step) => step.label === 'Approve')?.detail).toContain('locked')
  })

  it('attributes almost the whole run to the one model call', () => {
    // The point the old log-based UI buried: the model dominated the run and produced
    // nothing usable. If this ever stops being true the strip should stop claiming it.
    const developerShare = seat('developer').share
    expect(developerShare).toBeGreaterThan(0.9)
    expect(formatDuration(totalSpanMs(events))).toMatch(/^\d+\.\d\ds$/)
  })

  it('marks exactly the findings the security agent handed over', () => {
    const owned = selectedFindingIds(events)
    expect(owned.size).toBe(3)
    const unowned = run.findings.filter((finding) => !owned.has(finding.id))
    expect(unowned.map((finding) => finding.rule_id)).toEqual(['B404'])
  })

  it('shows the human bandit titles rather than the internal slugs', () => {
    const titles = run.findings.map((finding) => finding.title)
    expect(titles).not.toContain('blacklist')
    expect(titles).toContain('Starting a process with a partial executable path')
  })
})

describe('the same run part-way through, as a replay sees it', () => {
  it('does not borrow the final verdict for an agent still in flight', () => {
    const upToValidatorStart = events.slice(
      0,
      events.findIndex(
        (event) => event.agent === 'validator' && event.event_type === 'agent_started',
      ) + 1,
    )
    const partial = buildRoster(run, upToValidatorStart, true)
    const validator = partial.find((snapshot) => snapshot.definition.id === 'validator')!
    expect(validator.state).toBe('working')
    expect(validator.verdict).toBeNull()
    expect(partial.find((snapshot) => snapshot.definition.id === 'reviewer')!.state).toBe('idle')
  })
})
