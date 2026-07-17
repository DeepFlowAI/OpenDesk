'use client'
/**
 * High-risk confirmation dialog for takeover / force-hangup.
 *
 * Both require a mandatory reason (Select) and an optional note (Textarea,
 * 0–200 chars). When the reason is "other" the note becomes mandatory. The
 * confirm button uses destructive semantics and locks while submitting.
 */
import { useEffect, useMemo, useState } from 'react'
import { IconLoader2 } from '@tabler/icons-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const NOTE_MAX = 200

export type ReasonOption = { value: string; labelKey: string }

type Props = {
  open: boolean
  title: string
  body: string
  /** Info lines (agent, customer, participant count). */
  lines?: { label: string; value: string }[]
  reasonOptions: ReasonOption[]
  confirmLabel: string
  submitting?: boolean
  onConfirm: (reason: string, note: string) => void
  onClose: () => void
}

export function InterventionReasonDialog({
  open,
  title,
  body,
  lines,
  reasonOptions,
  confirmLabel,
  submitting = false,
  onConfirm,
  onClose,
}: Props) {
  const { locale } = useLocaleStore()
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')

  // Reset fields each time the dialog opens.
  useEffect(() => {
    if (open) {
      setReason('')
      setNote('')
    }
  }, [open])

  const noteRequired = reason === 'other'
  const canConfirm = useMemo(() => {
    if (!reason) return false
    if (noteRequired && !note.trim()) return false
    return true
  }, [reason, noteRequired, note])

  // Base UI's <Select.Value> can only resolve the selected label from the
  // popup's mounted items; inside this Dialog the popup unmounts on close, so
  // the trigger would fall back to the raw value (e.g. "agent_help"). Passing an
  // items map lets Value render the translated label without the popup open.
  const items = useMemo(
    () => Object.fromEntries(reasonOptions.map((o) => [o.value, t(o.labelKey, locale)])),
    [reasonOptions, locale],
  )

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !submitting) onClose() }}>
      <DialogContent className="gap-3 sm:max-w-[440px]">
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

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">
            {t('ws.records.callMonitor.reason.label', locale)}
          </label>
          <Select items={items} value={reason} onValueChange={(v) => setReason(v ?? '')} disabled={submitting}>
            <SelectTrigger aria-label={t('ws.records.callMonitor.reason.label', locale)}>
              <SelectValue placeholder={t('ws.records.callMonitor.reason.placeholder', locale)} />
            </SelectTrigger>
            <SelectContent>
              {reasonOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {t(opt.labelKey, locale)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">
            {t('ws.records.callMonitor.note.label', locale)}
            {noteRequired && <span className="ml-1 text-destructive">*</span>}
          </label>
          <Textarea
            value={note}
            maxLength={NOTE_MAX}
            disabled={submitting}
            onChange={(e) => setNote(e.target.value.slice(0, NOTE_MAX))}
            placeholder={t('ws.records.callMonitor.note.placeholder', locale)}
            aria-label={t('ws.records.callMonitor.note.label', locale)}
          />
          <span className="self-end text-xs text-muted-foreground tabular-nums">
            {note.length}/{NOTE_MAX}
          </span>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('ws.callbar.cancel', locale)}
          </Button>
          <Button
            variant="destructive"
            onClick={() => onConfirm(reason, note.trim())}
            disabled={submitting || !canConfirm}
          >
            {submitting && <IconLoader2 size={14} className="mr-1 animate-spin" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
