import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('renders the run status', () => {
    render(<StatusPill status="running" />)
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('labels a paused run as needing review rather than showing the raw status', () => {
    render(<StatusPill status="awaiting_review" />)
    expect(screen.getByText('needs review')).toBeInTheDocument()
  })
})
