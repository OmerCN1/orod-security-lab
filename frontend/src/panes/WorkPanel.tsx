import { useEffect, useMemo, useState } from 'react'
import { Code2, FileDiff, ShieldAlert } from 'lucide-react'
import { DiffViewer } from '../features/patch/DiffViewer'
import { FindingCard } from '../features/findings/FindingCard'
import type { RunRecord } from '../types'

type Tab = 'findings' | 'patch'

/**
 * The run's deliverable: what was found, and what was changed.
 *
 * The tab is deliberately *not* switched when a patch arrives. Moving the view out from
 * under someone mid-read is how the previous build lost their place.
 */
export function WorkPanel({
  run,
  ownedFindingIds,
}: {
  run: RunRecord | null
  ownedFindingIds: ReadonlySet<string>
}) {
  const changedFiles = useMemo(() => run?.patch?.changed_files ?? [], [run?.patch])
  const [tab, setTab] = useState<Tab>('findings')
  const [activeFile, setActiveFile] = useState<string | null>(null)

  useEffect(() => {
    setActiveFile((current) =>
      current && changedFiles.includes(current) ? current : (changedFiles[0] ?? null),
    )
  }, [changedFiles])

  // A new run starts on findings again; within one run the choice is the reader's.
  useEffect(() => setTab('findings'), [run?.id])

  if (!run) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="bar h-11 px-4">
          <span className="label">Work</span>
        </div>
        <div className="empty">Start a scan to see what the team finds and changes.</div>
      </div>
    )
  }

  const showDiff = tab === 'patch' && activeFile !== null

  return (
    <div className="flex min-w-0 flex-col">
      <div className="bar stick-sub h-11 justify-between px-4" style={{ background: 'var(--pane)' }}>
        <div className="flex gap-1" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'findings'}
            onClick={() => setTab('findings')}
            className={`tab ${tab === 'findings' ? 'tab-active' : ''}`}
          >
            <ShieldAlert size={14} /> What was found
            <span className="tab-count">{run.findings.length}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'patch'}
            disabled={changedFiles.length === 0}
            onClick={() => setTab('patch')}
            className={`tab ${tab === 'patch' ? 'tab-active' : ''}`}
          >
            <FileDiff size={14} /> What was changed
            <span className="tab-count">
              {changedFiles.length === 0 ? 'none' : `${changedFiles.length} file`}
            </span>
          </button>
        </div>
        <span className="mono truncate text-[11px]" style={{ color: 'var(--ghost)' }}>
          {run.repository_url}
        </span>
      </div>

      {tab === 'findings' ? (
        <div>
          {run.findings.length === 0 ? (
            <div className="empty">
              {run.status === 'completed'
                ? 'Scan completed with no reportable security findings.'
                : 'Bandit, Semgrep and OSV results merge here.'}
            </div>
          ) : (
            <div className="flex flex-col gap-2 p-3.5">
              {run.findings.map((finding) => (
                <FindingCard
                  key={finding.id}
                  finding={finding}
                  owned={ownedFindingIds.has(finding.id)}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div>
          {run.patch?.explanation && (
            <div
              className="flex shrink-0 gap-3 border-b p-3.5 divider"
              style={{ background: 'var(--raise)' }}
            >
              <span
                className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full"
                style={{
                  background: 'var(--raise-2)',
                  boxShadow: 'inset 0 0 0 1.5px var(--id-developer)',
                  color: 'var(--id-developer)',
                }}
              >
                <Code2 size={12} />
              </span>
              <p className="text-[12.5px] leading-[1.6]" style={{ color: 'var(--muted)' }}>
                <b className="font-medium" style={{ color: 'var(--text)' }}>
                  Developer:
                </b>{' '}
                “{run.patch.explanation}”
              </p>
            </div>
          )}

          {changedFiles.length > 1 && (
            <div className="flex shrink-0 gap-1.5 overflow-x-auto border-b px-3.5 py-2 divider">
              {changedFiles.map((file) => (
                <button
                  key={file}
                  type="button"
                  onClick={() => setActiveFile(file)}
                  className="mono shrink-0 rounded-md px-2.5 py-1 text-[11.5px] transition"
                  style={
                    file === activeFile
                      ? { background: 'var(--raise-2)', color: 'var(--text)' }
                      : { color: 'var(--faint)' }
                  }
                >
                  {file}
                </button>
              ))}
            </div>
          )}

          {showDiff ? (
            <DiffViewer runId={run.id} path={activeFile} />
          ) : (
            <div className="empty">No patch was produced for this run.</div>
          )}
        </div>
      )}
    </div>
  )
}
