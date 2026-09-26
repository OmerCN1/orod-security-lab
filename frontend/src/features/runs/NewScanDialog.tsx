import { useEffect, useRef, useState } from 'react'
import { Play, X } from 'lucide-react'
import type { ModelOption } from '../../types'

/**
 * Scanning is a once-per-run action, so it lives behind a button rather than occupying a
 * permanent column. The dialog is a native `<dialog>`: focus trapping, Escape and the
 * backdrop come from the platform instead of from hand-written key handlers.
 */
export function NewScanDialog({
  open,
  models,
  busy,
  onStart,
  onClose,
}: {
  open: boolean
  models: ModelOption[]
  busy: boolean
  onStart: (target: string, model: string | null, trusted: boolean) => void
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement | null>(null)
  const [target, setTarget] = useState('demo://vulnerable-python')
  const [model, setModel] = useState<string | null>(null)
  const [trusted, setTrusted] = useState(false)

  const close = () => {
    setTrusted(false)
    onClose()
  }

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const selected = models.find((option) => option.id === model)

  return (
    <dialog
      ref={ref}
      onClose={close}
      onClick={(event) => {
        // A click landing on the dialog element itself is a click on the backdrop.
        if (event.target === ref.current) close()
      }}
      className="m-auto w-[440px] max-w-[92vw] rounded-xl border p-0 backdrop:bg-black/60"
      style={{ borderColor: 'var(--line-strong)', background: 'var(--pane)', color: 'var(--text)' }}
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault()
          if (target.trim()) {
            onStart(target.trim(), model, trusted)
            setTrusted(false)
          }
        }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3 divider">
          <h2 className="text-[14px] font-semibold tracking-[-.01em]">New scan</h2>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            style={{ color: 'var(--faint)' }}
          >
            <X size={15} />
          </button>
        </div>

        <div className="flex flex-col gap-4 p-4">
          <div>
            <label className="label mb-1.5 block" htmlFor="scan-target">
              Target repository
            </label>
            <input
              id="scan-target"
              className="field"
              value={target}
              autoFocus
              spellCheck={false}
              onChange={(event) => {
                setTarget(event.target.value)
                setTrusted(false)
              }}
              placeholder="https://github.com/owner/repo"
            />
            <p className="mt-1.5 text-[11px] leading-[1.5]" style={{ color: 'var(--faint)' }}>
              An HTTPS github.com URL you can push to, or a <span className="mono">demo://</span>{' '}
              fixture.
            </p>
          </div>

          <div>
            <label className="label mb-1.5 block" htmlFor="scan-model">
              Model
            </label>
            <select
              id="scan-model"
              className="field"
              disabled={models.length === 0}
              value={model ?? ''}
              onChange={(event) => setModel(event.target.value || null)}
            >
              <option value="">Server default</option>
              {models.map((option) => (
                <option key={option.id} value={option.id} disabled={!option.available}>
                  {option.id}
                  {option.available ? '' : ' — unavailable'}
                </option>
              ))}
            </select>
            {selected && (
              <p className="mt-1.5 text-[11px] leading-[1.5]" style={{ color: 'var(--faint)' }}>
                {selected.detail}
              </p>
            )}
          </div>
          <label className="flex items-start gap-2 text-[12px] leading-5">
            <input
              type="checkbox"
              checked={trusted}
              onChange={(event) => setTrusted(event.target.checked)}
              className="mt-1"
            />
            <span>
              I trust this repository and allow its tests to run.
              <span className="mt-1 block" style={{ color: 'var(--muted)' }}>
                GitHub repository validation runs in an isolated, offline container.
                Demo tests run locally. Without consent, tests and publishing are blocked.
              </span>
            </span>
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t px-4 py-3 divider">
          <button type="button" className="btn-ghost" onClick={close}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy || !target.trim()}>
            <Play size={13} fill="currentColor" />
            {busy ? 'Starting…' : 'Start scan'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
