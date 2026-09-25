import { useState } from 'react'
import { Check, Lock, RotateCcw, UserRound, X } from 'lucide-react'
import type { ReviewDecision, ReviewRequest } from '../../types'

/**
 * The decision the run is blocked on. It docks to the bottom of the viewport rather than
 * sitting in a pane header, because it is the one thing the run needs from a person.
 *
 * Approve is disabled when validation failed *and says why* — the backend refuses such a
 * submission in two places, so a silently greyed button would misrepresent a hard rule as
 * a UI preference.
 */
export function DecisionBar({
  review,
  busy,
  onDecide,
}: {
  review: ReviewRequest
  busy: boolean
  onDecide: (decision: ReviewDecision, feedback?: string) => void
}) {
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedback, setFeedback] = useState('')
  const canSend = feedback.trim().length > 0

  return (
    <div
      className="sticky bottom-0 z-30 shrink-0 border-t px-4 py-3"
      style={{
        borderColor: 'rgba(251,191,36,.25)',
        background: 'linear-gradient(180deg, rgba(20,17,7,.97), rgba(12,14,19,.99))',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div className="flex flex-wrap items-center gap-4">
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-full"
          style={{
            background: 'var(--raise-2)',
            boxShadow: 'inset 0 0 0 1.5px var(--id-reviewer)',
            color: 'var(--id-reviewer)',
          }}
        >
          <UserRound size={14} />
        </span>

        <div className="min-w-0 flex-1 basis-[300px]">
          <p className="text-[13.5px] font-semibold" style={{ color: '#fde68a' }}>
            Your call
            {review.revision_count > 0 && (
              <span className="ml-2 font-normal" style={{ color: 'var(--muted)' }}>
                · revision {review.revision_count}
              </span>
            )}
          </p>
          <p className="mt-0.5 text-[12px] leading-[1.5]" style={{ color: 'var(--muted)' }}>
            {review.validation_summary || review.explanation || 'Awaiting your decision.'}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <button
            type="button"
            className="btn-success"
            disabled={busy || !review.can_approve}
            onClick={() => onDecide('approve')}
          >
            <Check size={13} strokeWidth={2.4} /> Approve &amp; open draft PR
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={busy}
            aria-expanded={feedbackOpen}
            onClick={() => setFeedbackOpen((open) => !open)}
          >
            <RotateCcw size={13} /> Send it back
          </button>
          <button type="button" className="btn-danger" disabled={busy} onClick={() => onDecide('reject')}>
            <X size={13} /> Reject
          </button>
        </div>
      </div>

      {!review.can_approve && (
        <p
          className="mt-2 inline-flex items-center gap-2 text-[11.5px]"
          style={{ color: 'var(--faint)' }}
        >
          <Lock size={12} style={{ color: 'var(--hold)' }} />
          Approve stays locked until validation passes. A failing patch can never open a pull request.
        </p>
      )}

      {feedbackOpen && (
        <div className="mt-3 max-w-[760px]">
          <label className="label mb-1.5 block" htmlFor="review-feedback">
            What should the Developer do differently?
          </label>
          <textarea
            id="review-feedback"
            className="field min-h-20 resize-y leading-[1.6]"
            autoFocus
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="e.g. remove shell=True — that is the high-severity finding, not the executable path"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <span className="text-[11.5px]" style={{ color: 'var(--faint)' }}>
              Goes to the Developer as reviewer feedback, and it tries again.
            </span>
            <span className="flex gap-2">
              <button type="button" className="btn-ghost" onClick={() => setFeedbackOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !canSend}
                onClick={() => onDecide('regenerate', feedback.trim())}
              >
                Send &amp; regenerate
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
