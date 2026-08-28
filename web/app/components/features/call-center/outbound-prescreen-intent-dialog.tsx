'use client'

import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { OutboundPrescreenIntentDraft } from '@/models/outbound-prescreen'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (intent: OutboundPrescreenIntentDraft) => void
}

export function OutboundPrescreenIntentDialog({ open, onOpenChange, onCreate }: Props) {
  const { locale } = useLocaleStore()
  const [name, setName] = useState('')
  const [threshold, setThreshold] = useState(0.86)

  const create = () => {
    const trimmed = name.trim()
    if (trimmed.length < 2 || trimmed.length > 20) return
    onCreate({
      name: trimmed,
      enabled: false,
      similarity_threshold: threshold,
      is_system: false,
      positive_examples: [],
      negative_examples: [],
    })
    setName('')
    setThreshold(0.86)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>{t('prescreen.createTitle', locale)}</DialogTitle>
          <DialogDescription>{t('prescreen.createDesc', locale)}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <label className="block text-sm font-medium">
            {t('prescreen.name', locale)}
            <Input className="mt-2" value={name} maxLength={20} onChange={(event) => setName(event.target.value)} placeholder={t('prescreen.namePlaceholder', locale)} />
            <span className="mt-1 block text-xs font-normal text-muted-foreground">{t('prescreen.nameHint', locale)}</span>
          </label>
          <label className="block text-sm font-medium">
            {t('prescreen.thresholdTitle', locale)}
            <Input className="mt-2 w-28 font-mono" type="number" min={0.5} max={0.99} step={0.01} value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          </label>
          <p className="rounded-lg border border-info/20 bg-info/5 p-3 text-xs text-muted-foreground">{t('prescreen.newDisabledHint', locale)}</p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('prescreen.cancel', locale)}</Button>
          <Button disabled={name.trim().length < 2 || name.trim().length > 20 || threshold < 0.5 || threshold > 0.99} onClick={create}>{t('prescreen.create', locale)}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
