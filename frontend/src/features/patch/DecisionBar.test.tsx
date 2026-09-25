import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReviewRequest } from '../../types'
import { DecisionBar } from './DecisionBar'

function review(partial: Partial<ReviewRequest> = {}): ReviewRequest {
  return {
    changed_files: ['app.py'],
    explanation: 'Removed shell execution',
    validation_passed: true,
    validation_summary: 'All fixed validation commands passed.',
    can_approve: true,
    revision_count: 0,
    requested_at: new Date().toISOString(),
    ...partial,
  }
}

describe('DecisionBar', () => {
  it('sends the approve decision', async () => {
    const onDecide = vi.fn()
    render(<DecisionBar review={review()} busy={false} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole('button', { name: /approve/i }))
    expect(onDecide).toHaveBeenCalledWith('approve')
  })

  it('locks approval and says why when validation failed', () => {
    render(
      <DecisionBar
        review={review({ can_approve: false, validation_passed: false })}
        busy={false}
        onDecide={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
    // A silently greyed button would misrepresent a hard backend rule as a UI preference.
    expect(screen.getByText(/never open a pull request/i)).toBeInTheDocument()
  })

  it('will not regenerate without feedback, then sends what was typed', async () => {
    const onDecide = vi.fn()
    render(<DecisionBar review={review()} busy={false} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole('button', { name: /send it back/i }))
    const send = screen.getByRole('button', { name: /send & regenerate/i })
    expect(send).toBeDisabled()

    await userEvent.type(screen.getByRole('textbox'), 'remove shell=True')
    await userEvent.click(send)
    expect(onDecide).toHaveBeenCalledWith('regenerate', 'remove shell=True')
  })

  it('rejects without asking for anything else', async () => {
    const onDecide = vi.fn()
    render(<DecisionBar review={review()} busy={false} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole('button', { name: /reject/i }))
    expect(onDecide).toHaveBeenCalledWith('reject')
  })

  it('disables every decision while one is in flight', () => {
    render(<DecisionBar review={review()} busy onDecide={vi.fn()} />)
    for (const name of [/approve/i, /send it back/i, /reject/i]) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
  })
})
