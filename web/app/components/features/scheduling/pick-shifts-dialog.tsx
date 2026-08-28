'use client'

import { useEffect, useState } from 'react'
import { IconCalendarOff } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Shift } from '@/models/scheduling'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

export type PickShiftsTarget =
  | { kind: 'cell'; employeeName: string; date: string; currentShiftIds: Set<number> }
  | { kind: 'batch'; cellCount: number }

export type PickShiftsDialogProps = {
  open: boolean
  target: PickShiftsTarget | null
  shifts: Shift[]
  submitting: boolean
  dayLabel: (date: string) => string
  onClose: () => void
  onSubmit: (selectedShiftIds: number[]) => void
}

export function PickShiftsDialog({
  open,
  target,
  shifts,
  submitting,
  dayLabel,
  onClose,
  onSubmit,
}: PickShiftsDialogProps) {
  const { locale } = useLocaleStore()
  const [selected, setSelected] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!open || !target) return
    setSelected(target.kind === 'cell' ? new Set(target.currentShiftIds) : new Set())
  }, [open, target])

  if (!target) return null

  const subtitle =
    target.kind === 'cell'
      ? t('scheduling.pickShifts.subtitle', locale, {
          name: target.employeeName,
          day: dayLabel(target.date),
        })
      : t('scheduling.pickShifts.subtitleBatch', locale, { count: target.cellCount })

  const toggle = (shift: Shift) => {
    setSelected((prev) => {
      if ((shift.shift_type ?? 'work') === 'leave') {
        return prev.has(shift.id) ? new Set() : new Set([shift.id])
      }
      const next = new Set(prev)
      for (const item of shifts) {
        if ((item.shift_type ?? 'work') === 'leave') next.delete(item.id)
      }
      if (next.has(shift.id)) next.delete(shift.id)
      else next.add(shift.id)
      return next
    })
  }

  const workShifts = shifts.filter((shift) => (shift.shift_type ?? 'work') === 'work')
  const leaveShifts = shifts.filter((shift) => shift.shift_type === 'leave')

  const renderShift = (shift: Shift) => {
    const checked = selected.has(shift.id)
    const isLeave = shift.shift_type === 'leave'
    return (
      <button
        key={shift.id}
        type="button"
        onClick={() => toggle(shift)}
        className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left hover:bg-muted/40"
      >
        <Checkbox checked={checked} tabIndex={-1} />
        <span
          className="grid h-5 w-5 shrink-0 place-items-center rounded-full text-white"
          style={{ background: shift.color }}
        >
          {isLeave && <IconCalendarOff size={12} />}
        </span>
        <span className="flex-1 text-sm font-medium">{shift.name}</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {isLeave
            ? t('scheduling.shifts.allDay', locale)
            : `${shift.start_time}–${shift.end_time}`}
        </span>
      </button>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-[440px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>{t('scheduling.pickShifts.title', locale)}</DialogTitle>
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        </DialogHeader>

        <div className="max-h-[360px] overflow-auto px-5 py-4">
          {shifts.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground">
              {t('scheduling.pickShifts.empty', locale)}
            </div>
          ) : (
            <div className="space-y-4">
              {workShifts.length > 0 && (
                <section className="space-y-2">
                  <div className="text-[11px] font-medium text-muted-foreground">
                    {t('scheduling.shiftType.work', locale)}
                  </div>
                  {workShifts.map(renderShift)}
                </section>
              )}
              {leaveShifts.length > 0 && (
                <section className="space-y-2 border-t border-border pt-3">
                  <div className="text-[11px] font-medium text-muted-foreground">
                    {t('scheduling.shiftType.leave', locale)}
                  </div>
                  {leaveShifts.map(renderShift)}
                </section>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button onClick={() => onSubmit([...selected])} disabled={submitting}>
            {t('scheduling.pickShifts.submit', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
