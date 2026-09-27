import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from '../../api/client'
import type { RunRecord } from '../../types'
import { useRun } from './useRun'

function runWith(status: RunRecord['status']): RunRecord {
  return { id: 'run-1', repository_url: 'demo://vulnerable-python', status } as RunRecord
}

afterEach(() => vi.restoreAllMocks())

describe('stopping a run', () => {
  it('shows the final state when the run finished before the cancel landed', async () => {
    vi.spyOn(client, 'subscribeToRun').mockReturnValue({ close: vi.fn() } as unknown as EventSource)
    vi.spyOn(client, 'cancelRun').mockRejectedValue(new Error('run is already completed'))
    const getRun = vi
      .spyOn(client, 'getRun')
      .mockResolvedValueOnce(runWith('running'))
      .mockResolvedValue(runWith('completed'))
    const { result } = renderHook(() => useRun())

    await act(() => result.current.open('run-1'))
    await act(() => result.current.stop())

    expect(getRun).toHaveBeenCalledTimes(2)
    expect(result.current.run?.status).toBe('completed')
    expect(result.current.error).toBe('run is already completed')
  })
})
