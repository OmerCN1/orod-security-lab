import type {
  FileContent,
  HealthResponse,
  ModelOption,
  ReviewDecision,
  RunEvent,
  RunRecord,
  RunSummary,
} from '../types'

/**
 * Same-origin by default: the dev server proxies `/api` to the backend and adds the API
 * token there, so it never reaches the browser.
 */
export const API_ROOT = import.meta.env.VITE_API_ROOT ?? '/api/v1'

/** Event names the backend emits; EventSource needs each one registered explicitly. */
const RUN_EVENT_TYPES = [
  'run',
  'agent_started',
  'agent_completed',
  'finding',
  'patch',
  'validation',
  'review',
  'pull_request',
] as const

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    throw new Error(await readError(response))
  }
  return response.json() as Promise<T>
}

/** FastAPI reports errors as `{detail: ...}`; surface that rather than raw JSON. */
async function readError(response: Response): Promise<string> {
  const body = await response.text()
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed.detail === 'string') return parsed.detail
    if (Array.isArray(parsed.detail)) {
      const first = parsed.detail[0] as { msg?: string } | undefined
      if (first?.msg) return first.msg
    }
  } catch {
    // Not JSON — fall through to the raw body.
  }
  return body || `Request failed (${response.status})`
}

export function getHealth(): Promise<HealthResponse> {
  return request('/health')
}

export function getModels(): Promise<ModelOption[]> {
  return request('/models')
}

export function listRuns(limit = 25): Promise<RunSummary[]> {
  return request(`/runs?limit=${limit}`)
}

export function createRun(repositoryUrl: string, model: string | null, trusted = false): Promise<RunRecord> {
  return request('/runs', {
    method: 'POST',
    body: JSON.stringify({ repository_url: repositoryUrl, trusted, model }),
  })
}

export function getRun(runId: string): Promise<RunRecord> {
  return request(`/runs/${runId}`)
}

export function getFileContent(
  runId: string,
  path: string,
  revision: 'working' | 'base' = 'working',
): Promise<FileContent> {
  const query = new URLSearchParams({ path, revision })
  return request(`/runs/${runId}/files/content?${query.toString()}`)
}

export function submitReview(
  runId: string,
  decision: ReviewDecision,
  feedback?: string,
): Promise<RunRecord> {
  return request(`/runs/${runId}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, feedback: feedback ?? null }),
  })
}

export function cancelRun(runId: string): Promise<RunRecord> {
  return request(`/runs/${runId}/cancel`, { method: 'POST' })
}

export function subscribeToRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onError: () => void,
  lastEventId = 0,
): EventSource {
  // The backend replays from Last-Event-ID, but EventSource cannot set headers, so the
  // cursor travels as a query parameter on reconnect.
  const query = lastEventId > 0 ? `?after=${lastEventId}` : ''
  const source = new EventSource(`${API_ROOT}/runs/${runId}/events${query}`)
  const handler = (raw: Event) => {
    onEvent(JSON.parse((raw as MessageEvent<string>).data) as RunEvent)
  }
  RUN_EVENT_TYPES.forEach((type) => source.addEventListener(type, handler))
  source.onerror = onError
  return source
}
