export type RunStatus =
  | 'queued'
  | 'running'
  | 'awaiting_review'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type ReviewDecision = 'approve' | 'reject' | 'regenerate'

export const TERMINAL_STATUSES: readonly RunStatus[] = ['completed', 'failed', 'cancelled']

export interface FileEntry {
  path: string
  size: number
  language: string | null
}

export interface FileContent {
  path: string
  content: string
  language: string | null
}

export interface Dependency {
  name: string
  version: string | null
  source_file: string
  ecosystem: string
}

export interface RepositorySnapshot {
  repository_url: string
  owner_repo: string | null
  base_branch: string
  workspace_path: string
  permission: string
  trusted: boolean
  files: FileEntry[]
  dependencies: Dependency[]
  summary: string
}

export interface Finding {
  id: string
  source: string
  rule_id: string
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical'
  confidence: string
  title: string
  message: string
  file_path: string | null
  line: number | null
  evidence: string | null
  remediation: string | null
  cwe_ids: string[]
  advisory_ids: string[]
  references: string[]
  deterministic: boolean
}

export interface PatchProposal {
  unified_diff: string
  changed_files: string[]
  finding_ids: string[]
  explanation: string
  validation_commands: string[][]
}

export interface Validation {
  passed: boolean
  summary: string
  new_high_findings: number
  commands: Array<{ argv: string[]; return_code: number; duration_ms: number }>
}

export interface PullRequest {
  url: string
  number: number | null
  branch: string
  draft: boolean
}

export interface ReviewRequest {
  changed_files: string[]
  explanation: string
  validation_passed: boolean
  validation_summary: string
  can_approve: boolean
  revision_count: number
  requested_at: string
}

export interface ModelOption {
  id: string
  provider: string
  available: boolean
  detail: string
  is_default: boolean
}

export interface RunSummary {
  id: string
  repository_url: string
  owner_repo: string | null
  model: string | null
  status: RunStatus
  phase: string
  created_at: string
  updated_at: string
  total_findings: number
  validation_passed: boolean | null
  pull_request_url: string | null
}

export interface RunRecord {
  id: string
  repository_url: string
  base_branch: string | null
  trusted: boolean
  model: string | null
  status: RunStatus
  phase: string
  created_at: string
  updated_at: string
  error: string | null
  repository: RepositorySnapshot | null
  findings: Finding[]
  patch: PatchProposal | null
  validation: Validation | null
  review: ReviewRequest | null
  pull_request: PullRequest | null
  metrics: {
    duration_ms: number
    total_findings: number
    findings_by_severity: Record<string, number>
    patch_generated: boolean
    validation_passed: boolean
    repair_attempts: number
    human_revisions: number
    review_decision: ReviewDecision | null
    pull_request_created: boolean
  } | null
}

export interface RunEvent {
  schema_version: string
  event_id: string
  sequence: number
  run_id: string
  timestamp: string
  agent: string
  event_type: string
  level: 'debug' | 'info' | 'warning' | 'error'
  message: string
  payload: Record<string, unknown>
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'unavailable'
  components: Record<string, { ok: boolean; detail: string }>
  models: Record<string, string>
  version: string
}
