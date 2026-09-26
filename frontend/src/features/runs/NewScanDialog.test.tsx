import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { NewScanDialog } from './NewScanDialog'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

function setup() {
  const onStart = vi.fn()
  const onClose = vi.fn()
  const props = { open: true, models: [], busy: false, onStart, onClose }
  const view = render(<NewScanDialog {...props} />)
  return { ...view, props, onStart, onClose }
}

describe('explicit repository trust', () => {
  it('starts with tests disabled, including for demos', async () => {
    const { onStart } = setup()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    expect(onStart).toHaveBeenCalledWith('demo://vulnerable-python', null, false)
  })

  it('forwards explicit consent and consumes it after submission', async () => {
    const { onStart } = setup()
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    expect(onStart).toHaveBeenCalledWith('demo://vulnerable-python', null, true)
    expect(screen.getByRole('checkbox')).not.toBeChecked()
  })

  it('does not carry consent to another repository', async () => {
    const { onStart } = setup()
    await userEvent.click(screen.getByRole('checkbox'))
    fireEvent.change(screen.getByLabelText('Target repository'), {
      target: { value: 'https://github.com/example/project' },
    })
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    expect(onStart).toHaveBeenCalledWith('https://github.com/example/project', null, false)
  })

  it('clears consent when cancelled and reopened', async () => {
    const { rerender, props, onClose } = setup()
    await userEvent.click(screen.getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    rerender(<NewScanDialog {...props} open={false} />)
    rerender(<NewScanDialog {...props} />)
    expect(screen.getByRole('checkbox')).not.toBeChecked()
  })
})
