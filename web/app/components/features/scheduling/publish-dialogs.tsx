'use client'

import { IconAlertTriangle, IconSend, IconRestore } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { RuleViolation } from '@/models/scheduling-rule'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { violationText, violationSubject } from './violation-utils'

/** Publish confirm: freezes the week's draft as the published snapshot. */
export function PublishDialog({
  open,
  hardViolations,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean
  hardViolations: RuleViolation[]
  submitting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onCancel() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex flex-col gap-0 overflow-hidden p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2">
            <IconSend size={16} className="text-primary" />
            {t('scheduling.board.publishDialog.title', locale)}
          </DialogTitle>
        </DialogHeader>
        <div className="max-h-[40vh] overflow-auto px-5 py-4">
          <p className="text-sm text-foreground">
            {t('scheduling.board.publishDialog.body', locale)}
          </p>
          {hardViolations.length > 0 && (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-xs font-medium text-red-700">
                <IconAlertTriangle size={14} />
                {t('scheduling.board.publishDialog.hardWarn', locale, {
                  count: hardViolations.length,
                })}
              </p>
              <ul className="mt-2 space-y-1.5">
                {hardViolations.slice(0, 3).map((v, i) => (
                  <li key={i} className="text-xs text-red-700">
                    <span className="font-medium">{violationSubject(v)}</span>
                    <span className="text-red-400"> · {v.date} · </span>
                    {violationText(v, locale)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onCancel} disabled={submitting} autoFocus>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={onConfirm} disabled={submitting}>
            {t('scheduling.board.publish', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Reset confirm: restores the draft from the published snapshot (destructive). */
export function ResetDialog({
  open,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean
  submitting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onCancel() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex flex-col gap-0 overflow-hidden p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2">
            <IconRestore size={16} className="text-destructive" />
            {t('scheduling.board.resetDialog.title', locale)}
          </DialogTitle>
        </DialogHeader>
        <div className="px-5 py-4">
          <p className="text-sm text-foreground">
            {t('scheduling.board.resetDialog.body', locale)}
          </p>
        </div>
        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onCancel} disabled={submitting} autoFocus>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={submitting}>
            {t('scheduling.board.resetConfirm', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
