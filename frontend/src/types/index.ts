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
  /** OSV findings only: the pinned dependency and the versions that fix the advisory. */
  dependency: Dependency | null
  fixed_versions: string[]
}

export interface FileEdit {
  path: string
  search: string
  replace: string
}

export interface PatchProposal {
  /** Rendered by the backend from `edits` for model patches; always the applied diff. */
  unified_diff: string
  changed_files: string[]
  finding_ids: string[]
  explanation: string
  validation_commands: string[][]
  /** The search/replace edits a model returned; empty for deterministic codemods. */
  edits: FileEdit[]
}

export interface ScannerRun {
  name: string
  ok: boolean
  findings: number
  detail: string
}

export interface Validation {
  passed: boolean
  summary: string
  new_high_findings: number
  /** Failures the base revision already had, left unchanged by the patch. */
  tolerated_failures: number
  /** `false` when pytest ran but collected no tests; `null` when none was attempted. */
  tests_ran: boolean | null
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
  scan_complete: boolean | null
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
  /** Per-scanner outcome of the initial scan; empty until it has run. */
  scanners: ScannerRun[]
  /** `false` when any scanner failed, so an empty findings list is not a clean result. */
  scan_complete: boolean | null
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
    scan_complete: boolean
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
