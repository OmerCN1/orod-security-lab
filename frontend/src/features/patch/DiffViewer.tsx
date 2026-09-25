import { useEffect, useState } from 'react'
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { getFileContent } from '../../api/client'

/**
 * Dark theme for the diff library, which styles through emotion rather than Tailwind.
 * Values mirror the tokens in index.css so the panel does not look bolted on.
 */
const diffStyles = {
  variables: {
    dark: {
      diffViewerBackground: '#07080b',
      diffViewerColor: '#e7eaf0',
      addedBackground: 'rgba(16, 185, 129, 0.10)',
      addedColor: '#c9f5e3',
      removedBackground: 'rgba(244, 63, 94, 0.10)',
      removedColor: '#ffd7de',
      wordAddedBackground: 'rgba(16, 185, 129, 0.28)',
      wordRemovedBackground: 'rgba(244, 63, 94, 0.28)',
      gutterBackground: '#0c0e13',
      gutterColor: '#5b6273',
      addedGutterBackground: 'rgba(16, 185, 129, 0.16)',
      removedGutterBackground: 'rgba(244, 63, 94, 0.16)',
      highlightBackground: '#12151d',
      codeFoldBackground: '#0c0e13',
      codeFoldGutterBackground: '#0c0e13',
      codeFoldContentColor: '#8d95a5',
      emptyLineBackground: '#07080b',
    },
  },
  line: { fontSize: '11.5px', lineHeight: '1.8' },
  gutter: { fontSize: '10.5px', minWidth: '36px', width: '36px' },
  // The library floors `.diff-container` at `min-width: 1000px`, which is wider than the
  // work column. Its own `width: 100%` never wins, so the "after" side was clipped at the
  // panel edge with the only horizontal scrollbar stranded at the bottom of a tall diff.
  // Releasing the floor lets the fixed layout share the real width between the two sides.
  diffContainer: { minWidth: 0, width: '100%', tableLayout: 'fixed' as const },
  contentText: { wordBreak: 'break-word' as const, whiteSpace: 'pre-wrap' as const },
}

export function DiffViewer({ runId, path }: { runId: string; path: string }) {
  const [sides, setSides] = useState<{ base: string; working: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setSides(null)
    setError(null)
    // The patch is applied but never committed, so the base side comes from HEAD.
    Promise.all([
      getFileContent(runId, path, 'base').then((file) => file.content).catch(() => ''),
      getFileContent(runId, path, 'working').then((file) => file.content),
    ])
      .then(([base, working]) => {
        if (!cancelled) setSides({ base, working })
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load diff')
      })
    return () => {
      cancelled = true
    }
  }, [runId, path])

  if (error) return <div className="empty">{error}</div>
  if (!sides) return <div className="empty">Loading diff…</div>

  return (
    <div className="min-w-0 overflow-x-auto text-[11px]">
      <ReactDiffViewer
        oldValue={sides.base}
        newValue={sides.working}
        splitView
        useDarkTheme
        compareMethod={DiffMethod.WORDS}
        leftTitle="Before"
        rightTitle="After · agent patch"
        styles={diffStyles}
      />
    </div>
  )
}
