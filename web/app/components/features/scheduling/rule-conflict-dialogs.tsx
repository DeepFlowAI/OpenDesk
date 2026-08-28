'use client'

import { IconAlertTriangle } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { RuleViolation } from '@/models/scheduling-rule'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { violationText, violationSubject } from './violation-utils'

function ViolationList({ violations, tone }: { violations: RuleViolation[]; tone: 'hard' | 'soft' }) {
  const { locale } = useLocaleStore()
  return (
    <ul className="space-y-2">
      {violations.map((v, i) => (
        <li
          key={i}
          className={`rounded-lg border px-3 py-2.5 text-xs ${
            tone === 'hard'
              ? 'border-red-200 bg-red-50/70'
              : 'border-amber-200 bg-amber-50/60'
          }`}
        >
          <span className="font-medium">{violationSubject(v)}</span>
          <span className="text-muted-foreground"> · {v.date} · </span>
          <span>{violationText(v, locale)}</span>
        </li>
      ))}
    </ul>
  )
}

/** Hard-constraint block: the write was rejected; acknowledge only. */
export function HardBlockDialog({
  open,
  violations,
  onClose,
}: {
  open: boolean
  violations: RuleViolation[]
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex flex-col gap-0 p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2">
            <IconAlertTriangle size={16} className="text-red-600" />
            {t('scheduling.hardBlock.title', locale)}
          </DialogTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('scheduling.hardBlock.subtitle', locale)}
          </p>
        </DialogHeader>
        <div className="max-h-[40vh] overflow-auto px-5 py-4">
          <ViolationList violations={violations} tone="hard" />
        </div>
        <DialogFooter className="px-5 py-4">
          <Button onClick={onClose}>{t('scheduling.hardBlock.ok', locale)}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Soft-constraint warning: confirm to retry the write with allow_soft. */
export function SoftWarnDialog({
  open,
  violations,
  submitting,
  onCancel,
  onConfirm,
}: {
  open: boolean
  violations: RuleViolation[]
  submitting: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onCancel() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex flex-col gap-0 p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex items-center gap-2">
            <IconAlertTriangle size={16} className="text-amber-600" />
            {t('scheduling.softWarn.title', locale)}
          </DialogTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('scheduling.softWarn.subtitle', locale)}
          </p>
        </DialogHeader>
        <div className="max-h-[40vh] overflow-auto px-5 py-4">
          <ViolationList violations={violations} tone="soft" />
          <p className="mt-3 text-xs text-muted-foreground">
            {t('scheduling.softWarn.note', locale)}
          </p>
        </div>
        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onCancel} disabled={submitting}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={onConfirm} disabled={submitting}>
            {t('scheduling.softWarn.continue', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
