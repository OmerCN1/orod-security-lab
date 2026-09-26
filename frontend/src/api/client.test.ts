import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRun } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('createRun consent', () => {
  it.each([undefined, false, true])('sends only the supplied consent: %s', async (trusted) => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'run' }) })
    vi.stubGlobal('fetch', fetch)
    await createRun('https://github.com/example/project', null, trusted)
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      repository_url: 'https://github.com/example/project', model: null, trusted: trusted ?? false,
    })
  })
})
