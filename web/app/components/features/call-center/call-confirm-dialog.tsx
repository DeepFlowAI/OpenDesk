'use client'
/**
 * Small centered confirm dialog for irreversible in-call actions
 * (direct transfer, end-all). Title/body/lines and confirm label are provided
 * by the caller; the confirm button uses destructive semantics.
 */
import { IconLoader2 } from '@tabler/icons-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type Props = {
  open: boolean
  title: string
  body: string
  /** Extra key/value lines shown between body and actions. */
  lines?: { label: string; value: string }[]
  confirmLabel: string
  submitting?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function CallConfirmDialog({
  open,
  title,
  body,
  lines,
  confirmLabel,
  submitting = false,
  onConfirm,
  onClose,
}: Props) {
  const { locale } = useLocaleStore()
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !submitting) onClose() }}>
      <DialogContent className="gap-3 sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{body}</DialogDescription>
        </DialogHeader>
        {lines && lines.length > 0 && (
          <dl className="space-y-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
            {lines.map((line) => (
              <div key={line.label} className="flex justify-between gap-3">
                <dt className="text-muted-foreground">{line.label}</dt>
                <dd className="font-medium text-foreground">{line.value}</dd>
              </div>
            ))}
          </dl>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('ws.callbar.cancel', locale)}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={submitting}>
            {submitting && <IconLoader2 size={14} className="mr-1 animate-spin" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
