'use client'

import { useEffect, useState } from 'react'
import { IconCalendarOff } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Shift, ShiftType } from '@/models/scheduling'
import { useCreateShift, useUpdateShift } from '@/service/use-scheduling'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { TimeInput } from '@/components/ui/time-input'
import { RampColorPalette } from '@/components/ui/ramp-color-palette'

export type ShiftFormDialogProps = {
  open: boolean
  /** null for create, shift for edit */
  shift: Shift | null
  defaultType?: ShiftType
  /** Used when creating; defaults to 1 */
  nextSortOrder?: number
  onClose: () => void
}

type FormState = {
  name: string
  shift_type: ShiftType
  start_time: string
  end_time: string
  color: string
}

const INITIAL: FormState = {
  name: '',
  shift_type: 'work',
  start_time: '',
  end_time: '',
  color: '',
}

export function ShiftFormDialog({
  open,
  shift,
  defaultType = 'work',
  nextSortOrder = 1,
  onClose,
}: ShiftFormDialogProps) {
  const { locale } = useLocaleStore()
  const [form, setForm] = useState<FormState>(INITIAL)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState | 'time', string>>>({})
  const createMutation = useCreateShift()
  const updateMutation = useUpdateShift()
  const submitting = createMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if (!open) return
    setErrors({})
    if (shift) {
      setForm({
        name: shift.name,
        shift_type: shift.shift_type ?? 'work',
        start_time: shift.start_time,
        end_time: shift.end_time,
        color: shift.color,
      })
    } else {
      setForm({ ...INITIAL, shift_type: defaultType })
    }
  }, [defaultType, open, shift])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined, time: undefined }))
  }

  const isLeave = form.shift_type === 'leave'
  const typeLocked = Boolean(shift && (shift.has_references ?? shift.has_assignments))
  const overnight = !isLeave
    && form.start_time !== ''
    && form.end_time !== ''
    && form.end_time <= form.start_time

  const validate = (): boolean => {
    const next: typeof errors = {}
    const name = form.name.trim()
    if (!name) next.name = t('scheduling.form.err.nameRequired', locale)
    else if (name.length > 20) next.name = t('scheduling.form.err.nameTooLong', locale)
    if (!isLeave) {
      if (!form.start_time || !form.end_time) next.time = t('scheduling.form.err.timeRequired', locale)
      else if (form.start_time === form.end_time) next.time = t('scheduling.form.err.timeEqual', locale)
    }
    if (!form.color) next.color = t('scheduling.form.err.colorRequired', locale)
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const submit = async () => {
    if (!validate()) return
    const base = {
      name: form.name.trim(),
      shift_type: form.shift_type,
      ...(isLeave ? {} : { start_time: form.start_time, end_time: form.end_time }),
      color: form.color,
    }
    try {
      if (shift) {
        await updateMutation.mutateAsync({ id: shift.id, ...base })
      } else {
        await createMutation.mutateAsync({
          ...base,
          sort_order: Math.min(999, Math.max(1, nextSortOrder)),
        })
      }
      toast.success(t('scheduling.shifts.toast.saved', locale))
      onClose()
    } catch {
      toast.error(t('scheduling.shifts.toast.saveFailed', locale))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>
            {shift
              ? t('scheduling.form.editTitle', locale)
              : t('scheduling.form.newTitle', locale)}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 overflow-y-auto px-6 py-4">
          <div>
            <Label className="mb-1.5 text-xs font-medium">
              {t('scheduling.form.type', locale)} <span className="text-destructive">*</span>
            </Label>
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
              {(['work', 'leave'] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  disabled={typeLocked}
                  onClick={() => set('shift_type', type)}
                  className={`h-8 rounded-md px-3 text-sm font-medium transition-colors ${
                    form.shift_type === type
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  } disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  {t(`scheduling.shiftType.${type}`, locale)}
                </button>
              ))}
            </div>
            {typeLocked && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                {t('scheduling.form.typeLocked', locale)}
              </p>
            )}
          </div>

          <div>
            <Label className="mb-1.5 text-xs font-medium">
              {t('scheduling.form.name', locale)} <span className="text-destructive">*</span>
            </Label>
            <Input
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder={t(
                isLeave
                  ? 'scheduling.form.leaveNamePlaceholder'
                  : 'scheduling.form.namePlaceholder',
                locale,
              )}
              maxLength={20}
            />
            {errors.name && <p className="mt-1 text-[11px] text-destructive">{errors.name}</p>}
          </div>

          {isLeave ? (
            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3">
              <IconCalendarOff className="mt-0.5 shrink-0 text-muted-foreground" size={16} />
              <p className="text-xs leading-5 text-muted-foreground">
                {t('scheduling.form.leaveAllDayTip', locale)}
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="mb-1.5 text-xs font-medium">
                    {t('scheduling.form.startTime', locale)} <span className="text-destructive">*</span>
                  </Label>
                  <TimeInput
                    value={form.start_time}
                    onChange={(e) => set('start_time', e.target.value)}
                  />
                </div>
                <div>
                  <Label className="mb-1.5 text-xs font-medium">
                    {t('scheduling.form.endTime', locale)} <span className="text-destructive">*</span>
                  </Label>
                  <TimeInput
                    value={form.end_time}
                    onChange={(e) => set('end_time', e.target.value)}
                  />
                </div>
              </div>
              {errors.time && <p className="-mt-2 text-[11px] text-destructive">{errors.time}</p>}
              {overnight && !errors.time && (
                <p className="-mt-2 text-[11px] text-amber-700">
                  {t('scheduling.form.overnightTip', locale)}
                </p>
              )}
            </>
          )}

          <div>
            <Label className="mb-1.5 text-xs font-medium">
              {t('scheduling.form.color', locale)} <span className="text-destructive">*</span>
            </Label>
            <RampColorPalette
              selectedColor={form.color || null}
              onSelect={(hex) => set('color', hex)}
            />
            {errors.color && <p className="mt-1 text-[11px] text-destructive">{errors.color}</p>}
          </div>
        </div>

        <DialogFooter className="px-6 py-4">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting
              ? t('scheduling.form.submitting', locale)
              : t('scheduling.form.submit', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
