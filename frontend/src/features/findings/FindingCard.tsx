import { Code2, ExternalLink, UserRound } from 'lucide-react'
import type { Finding } from '../../types'

const SEVERITY: Record<Finding['severity'], { chip: string; text: string; stripe: string }> = {
  critical: { chip: 'rgba(251,113,133,.18)', text: '#fda4af', stripe: 'var(--fail)' },
  high: { chip: 'rgba(251,113,133,.16)', text: '#fda4af', stripe: 'var(--fail)' },
  medium: { chip: 'rgba(251,191,36,.16)', text: '#fcd34d', stripe: 'var(--hold)' },
  low: { chip: 'rgba(79,156,249,.15)', text: '#93c5fd', stripe: 'var(--accent)' },
  info: { chip: 'rgba(255,255,255,.07)', text: 'var(--muted)', stripe: 'var(--ghost)' },
}

export function FindingCard({ finding, owned }: { finding: Finding; owned: boolean }) {
  const tone = SEVERITY[finding.severity]
  // Bandit's issue_text is now the title, so a message identical to it adds nothing.
  const message = finding.message.replace(/\.$/, '') === finding.title ? null : finding.message

  return (
    <article
      className="grid grid-cols-[3px_minmax(0,1fr)] overflow-hidden rounded-[9px] border transition"
      style={{ borderColor: 'var(--line)', background: 'var(--pane)' }}
    >
      <span style={{ background: tone.stripe }} />
      <div className="min-w-0 p-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <span
            className="mono rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-[.11em]"
            style={{ background: tone.chip, color: tone.text }}
          >
            {finding.severity}
          </span>
          <span className="mono text-[10.5px]" style={{ color: 'var(--ghost)' }}>
            {finding.source} · {finding.rule_id}
          </span>
        </div>

        <h3 className="mt-2 text-[13.5px] font-medium leading-[1.4]">{finding.title}</h3>
        {message && (
          <p className="mt-1 text-[12.5px] leading-[1.55]" style={{ color: 'var(--muted)' }}>
            {message}
          </p>
        )}

        <div className="mt-2.5 flex flex-wrap items-center gap-2.5">
          {finding.file_path && (
            <span className="mono text-[11px]" style={{ color: '#93c5fd' }}>
              {finding.file_path}
              {finding.line ? `:${finding.line}` : ''}
            </span>
          )}
          {finding.dependency && finding.fixed_versions.length > 0 && (
            <span className="mono text-[11px]" style={{ color: 'var(--muted)' }}>
              {finding.dependency.name} {finding.dependency.version} · fixed in{' '}
              {finding.fixed_versions.join(', ')}
            </span>
          )}
          <span
            className="inline-flex items-center gap-1.5 rounded-full py-0.5 pl-0.5 pr-2.5 text-[11px]"
            style={{ border: '1px solid var(--line)', color: 'var(--muted)' }}
          >
            <span
              className="grid h-[15px] w-[15px] place-items-center rounded-full"
              style={{
                background: 'var(--raise-2)',
                boxShadow: `inset 0 0 0 1px ${owned ? 'var(--id-developer)' : 'var(--id-reviewer)'}`,
                color: owned ? 'var(--id-developer)' : 'var(--id-reviewer)',
              }}
            >
              {owned ? <Code2 size={8} /> : <UserRound size={8} />}
            </span>
            {owned ? 'Developer takes it' : 'You take it'}
          </span>
          {finding.references[0] && (
            <a
              className="inline-flex items-center gap-1 text-[11px] transition hover:underline"
              style={{ color: 'var(--faint)' }}
              href={finding.references[0]}
              target="_blank"
              rel="noreferrer"
            >
              Advisory <ExternalLink size={10} />
            </a>
          )}
        </div>
      </div>
    </article>
  )
}
