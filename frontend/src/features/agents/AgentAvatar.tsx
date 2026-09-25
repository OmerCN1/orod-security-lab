import { Building2, Check, Code2, Minus, Pause, ScanSearch, ShieldCheck, UserRound, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AgentId, AgentState } from './roster'

const ICONS: Record<AgentId, LucideIcon> = {
  architect: Building2,
  security: ScanSearch,
  developer: Code2,
  validator: ShieldCheck,
  reviewer: UserRound,
}

/** Identity is carried by the ring only. Filling the avatar would give five agents five themes. */
const RING: Record<AgentId, string> = {
  architect: 'var(--id-architect)',
  security: 'var(--id-security)',
  developer: 'var(--id-developer)',
  validator: 'var(--id-validator)',
  reviewer: 'var(--id-reviewer)',
}

const BADGE: Record<AgentState, { background: string; halo?: string; icon: LucideIcon | null }> = {
  idle: { background: 'var(--ghost)', icon: null },
  working: { background: 'var(--busy)', halo: 'rgba(79,156,249,.55)', icon: null },
  waiting: { background: 'var(--hold)', halo: 'rgba(251,191,36,.55)', icon: Pause },
  done: { background: 'var(--pass)', icon: Check },
  attention: { background: 'var(--hold)', icon: Minus },
  failed: { background: 'var(--fail)', icon: X },
}

export function AgentAvatar({
  id,
  state,
  size = 34,
}: {
  id: AgentId
  state: AgentState
  size?: number
}) {
  const Icon = ICONS[id]
  const badge = BADGE[state]
  const BadgeIcon = badge.icon
  const badgeSize = Math.round(size * 0.41)
  const animated = state === 'working' || state === 'waiting'

  return (
    <span
      className="relative grid shrink-0 place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: 'var(--raise-2)',
        boxShadow: `inset 0 0 0 1.5px ${RING[id]}`,
        color: RING[id],
      }}
    >
      <Icon size={Math.round(size * 0.44)} strokeWidth={1.9} />
      <span
        className={`absolute grid place-items-center rounded-full ${animated ? 'breathe' : ''}`}
        style={{
          right: -2,
          bottom: -2,
          width: badgeSize,
          height: badgeSize,
          background: badge.background,
          border: '2px solid var(--pane)',
          ...(badge.halo ? ({ '--halo': badge.halo } as React.CSSProperties) : {}),
        }}
      >
        {BadgeIcon && <BadgeIcon size={Math.round(badgeSize * 0.55)} strokeWidth={4} color="#06080c" />}
      </span>
    </span>
  )
}
