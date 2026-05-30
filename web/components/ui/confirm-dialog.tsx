'use client'
/**
 * Shared confirm dialog.
 *
 * Several pages duplicated this card layout (ticket-views, session-summary,
 * organization-fields, etc.). New code should use this component; existing
 * inline copies can migrate incrementally.
 *
 * Usage:
 *
 *   const [open, setOpen] = useState(false)
 *   <button onClick={() => setOpen(true)}>Delete</button>
 *   <ConfirmDialog
 *     open={open}
 *     title="删除规则"
 *     message="此操作不可恢复"
 *     itemName={rule.name}
 *     confirmLabel="确定删除"
 *     variant="destructive"
 *     onCancel={() => setOpen(false)}
 *     onConfirm={async () => { await del(); setOpen(false) }}
 *   />
 */
import { useEffect } from 'react'

type Variant = 'default' | 'destructive'

export type ConfirmDialogProps = {
  open: boolean
  title: string
  message?: string
  /** Optional emphasized item name (e.g. record being deleted). */
  itemName?: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: Variant
  loading?: boolean
  onCancel: () => void
  onConfirm: () => void | Promise<void>
}

export function ConfirmDialog({
  open,
  title,
  message,
  itemName,
  confirmLabel = '确定',
  cancelLabel = '取消',
  variant = 'default',
  loading = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  // ESC to cancel
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  const confirmClass =
    variant === 'destructive'
      ? 'bg-destructive text-white hover:bg-destructive/90'
      : 'bg-black text-white hover:bg-black/85'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onCancel}
    >
      <div
        className="w-[420px] max-w-[90vw] rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        {message && <p className="mt-3 text-sm text-muted-foreground">{message}</p>}
        {itemName && (
          <div className="mt-3 rounded-lg border border-border p-3">
            <p className="text-sm font-medium text-foreground">{itemName}</p>
          </div>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="flex h-9 items-center rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`flex h-9 items-center rounded-lg px-4 text-sm font-medium transition-colors disabled:opacity-50 ${confirmClass}`}
          >
            {loading ? '...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
