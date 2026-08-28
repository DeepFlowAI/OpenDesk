'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { RotationTemplate, RotationTemplateDay } from '@/models/scheduling-rule'
import type { Shift } from '@/models/scheduling'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
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

const MIN_DAYS = 2
const MAX_DAYS = 28

export type RotationTemplateDialogProps = {
  open: boolean
  /** Existing template to edit; null = create new. */
  template: RotationTemplate | null
  shifts: Shift[]
  onClose: () => void
  onSave: (template: RotationTemplate) => void
}

export function RotationTemplateDialog({
  open,
  template,
  shifts,
  onClose,
  onSave,
}: RotationTemplateDialogProps) {
  const { locale } = useLocaleStore()
  const enabledShifts = useMemo(() => shifts.filter((s) => s.is_enabled), [shifts])
  const shiftItems = useMemo(
    () => Object.fromEntries(enabledShifts.map((s) => [String(s.id), s.name])),
    [enabledShifts],
  )

  const [name, setName] = useState('')
  const [days, setDays] = useState<RotationTemplateDay[]>([])
  const [isDefault, setIsDefault] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setName(template?.name ?? '')
    setDays(
      template?.days ?? [
        { kind: 'shift', shift_id: enabledShifts[0]?.id ?? 0 },
        { kind: 'off' },
      ],
    )
    setIsDefault(template?.is_default ?? false)
    setError('')
  }, [open, template, enabledShifts])

  const setDay = (index: number, day: RotationTemplateDay) => {
    setDays((prev) => prev.map((d, i) => (i === index ? day : d)))
  }

  const shiftById = (id: number) => enabledShifts.find((s) => s.id === id)

  const handleSave = () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setError(t('scheduling.rules.template.err.nameRequired', locale))
      return
    }
    if (days.some((d) => d.kind === 'shift' && !shiftById(d.shift_id))) {
      setError(t('scheduling.rules.template.err.shiftRequired', locale))
      return
    }
    onSave({
      id: template?.id ?? `t_${Date.now()}`,
      name: trimmed,
      is_default: isDefault,
      days,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent className="gap-0 p-0 sm:max-w-[560px]">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>
            {template
              ? t('scheduling.rules.template.editTitle', locale)
              : t('scheduling.rules.template.newTitle', locale)}
          </DialogTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('scheduling.rules.template.subtitle', locale)}
          </p>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto px-5 py-4">
          <label className="block text-xs text-muted-foreground">
            {t('scheduling.rules.template.name', locale)}
            <Input
              className="mt-1"
              value={name}
              maxLength={40}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('scheduling.rules.template.namePlaceholder', locale)}
            />
          </label>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground">
                {t('scheduling.rules.template.days', locale, {
                  count: days.length,
                  min: MIN_DAYS,
                  max: MAX_DAYS,
                })}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={days.length >= MAX_DAYS}
                onClick={() =>
                  setDays((prev) => [
                    ...prev,
                    { kind: 'shift', shift_id: enabledShifts[0]?.id ?? 0 },
                  ])
                }
              >
                <IconPlus size={12} />
                {t('scheduling.rules.template.addDay', locale)}
              </Button>
            </div>

            <div className="space-y-2 rounded-lg border border-border p-3">
              {days.map((day, index) => (
                <div
                  key={index}
                  className="flex items-center gap-2 rounded-md border border-border bg-muted/20 px-2.5 py-2"
                >
                  <span className="w-10 shrink-0 text-xs font-medium text-muted-foreground">
                    {t('scheduling.rules.template.dayN', locale, { n: index + 1 })}
                  </span>
                  <div className="inline-flex h-8 items-center rounded-md border border-border bg-background p-0.5 text-[11px]">
                    <button
                      type="button"
                      className={`rounded px-2 py-1 ${
                        day.kind === 'shift'
                          ? 'bg-primary/10 font-medium text-primary'
                          : 'text-muted-foreground'
                      }`}
                      onClick={() =>
                        setDay(index, { kind: 'shift', shift_id: enabledShifts[0]?.id ?? 0 })
                      }
                    >
                      {t('scheduling.rules.template.kindShift', locale)}
                    </button>
                    <button
                      type="button"
                      className={`rounded px-2 py-1 ${
                        day.kind === 'off'
                          ? 'bg-muted font-medium text-foreground'
                          : 'text-muted-foreground'
                      }`}
                      onClick={() => setDay(index, { kind: 'off' })}
                    >
                      {t('scheduling.rules.template.kindOff', locale)}
                    </button>
                  </div>
                  {day.kind === 'shift' ? (
                    <Select
                      items={shiftItems}
                      value={String(day.shift_id)}
                      onValueChange={(v) => setDay(index, { kind: 'shift', shift_id: Number(v) })}
                    >
                      <SelectTrigger className="h-8 flex-1" aria-label={t('scheduling.rules.template.kindShift', locale)}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {enabledShifts.map((s) => (
                          <SelectItem key={s.id} value={String(s.id)}>
                            {s.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="flex h-8 flex-1 items-center rounded-md border border-dashed border-border px-2 text-xs text-muted-foreground">
                      {t('scheduling.rules.template.offDay', locale)}
                    </div>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="px-2"
                    disabled={days.length <= MIN_DAYS}
                    onClick={() => setDays((prev) => prev.filter((_, i) => i !== index))}
                    aria-label={t('scheduling.rules.template.removeDay', locale)}
                  >
                    <IconTrash size={14} />
                  </Button>
                </div>
              ))}
            </div>

            <p className="mt-2 text-[11px] text-muted-foreground">
              {t('scheduling.rules.template.preview', locale)}
              {days.map((d, i) => (
                <span key={i}>
                  {i > 0 ? ' → ' : ' '}
                  <span className={d.kind === 'off' ? 'text-muted-foreground' : 'font-medium text-foreground'}>
                    {d.kind === 'off'
                      ? t('scheduling.rules.template.kindOff', locale)
                      : (shiftById(d.shift_id)?.name ?? '—')}
                  </span>
                </span>
              ))}
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <Switch checked={isDefault} onCheckedChange={setIsDefault} />
            <span>{t('scheduling.rules.template.setDefault', locale)}</span>
          </label>

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onClose}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={handleSave}>{t('scheduling.rules.template.save', locale)}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
