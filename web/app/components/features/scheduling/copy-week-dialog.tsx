'use client'

import { useEffect, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

export type CopyWeekDialogProps = {
  open: boolean
  submitting: boolean
  onClose: () => void
  onSubmit: (mode: 'skip' | 'overwrite') => void
}

export function CopyWeekDialog({ open, submitting, onClose, onSubmit }: CopyWeekDialogProps) {
  const { locale } = useLocaleStore()
  const [mode, setMode] = useState<'skip' | 'overwrite'>('skip')

  useEffect(() => {
    if (open) setMode('skip')
  }, [open])

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex flex-col gap-0 p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>{t('scheduling.copyWeek.title', locale)}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 px-5 py-4 text-sm">
          <p className="leading-6 text-muted-foreground">
            {t('scheduling.copyWeek.desc', locale)}
          </p>
          <RadioGroup value={mode} onValueChange={(v) => setMode(v as 'skip' | 'overwrite')}>
            {(['skip', 'overwrite'] as const).map((value) => (
              <label
                key={value}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 ${
                  mode === value ? 'border-primary bg-primary/5' : 'border-border'
                }`}
              >
                <RadioGroupItem value={value} className="mt-0.5" />
                <span>
                  <span className="font-medium">{t(`scheduling.copyWeek.${value}`, locale)}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {t(`scheduling.copyWeek.${value}Desc`, locale)}
                  </span>
                </span>
              </label>
            ))}
          </RadioGroup>
        </div>

        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={() => onSubmit(mode)} disabled={submitting}>
            {t('scheduling.copyWeek.submit', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
