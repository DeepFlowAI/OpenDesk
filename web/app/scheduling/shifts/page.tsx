'use client'

import { useEffect, useState } from 'react'
import { IconCalendarOff, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Shift, ShiftType } from '@/models/scheduling'
import { useDeleteShift, useShifts, useUpdateShift } from '@/service/use-scheduling'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ShiftFormDialog } from '@/app/components/features/scheduling/shift-form-dialog'

function SortOrderCell({
  shift,
  disabled,
  label,
  onSave,
}: {
  shift: Shift
  disabled?: boolean
  label: string
  onSave: (sortOrder: number) => Promise<void>
}) {
  const [value, setValue] = useState(String(shift.sort_order))

  useEffect(() => {
    setValue(String(shift.sort_order))
  }, [shift.sort_order])

  const commit = async () => {
    const next = Number(value)
    if (!Number.isInteger(next) || next < 1 || next > 999) {
      setValue(String(shift.sort_order))
      return
    }
    if (next === shift.sort_order) return
    await onSave(next)
  }

  return (
    <Input
      type="number"
      min={1}
      max={999}
      disabled={disabled}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        void commit()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.currentTarget.blur()
        }
      }}
      className="h-8 w-16 text-center tabular-nums"
      aria-label={label}
    />
  )
}

export default function SchedulingShiftsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useShifts()
  const updateMutation = useUpdateShift()
  const deleteMutation = useDeleteShift()

  const [typeFilter, setTypeFilter] = useState<'all' | ShiftType>('all')
  const [form, setForm] = useState<{
    open: boolean
    shift: Shift | null
    defaultType: ShiftType
  }>({
    open: false,
    shift: null,
    defaultType: 'work',
  })
  const [deleteTarget, setDeleteTarget] = useState<Shift | null>(null)
  const [deleting, setDeleting] = useState(false)

  const shifts = data?.items ?? []
  const visibleShifts = typeFilter === 'all'
    ? shifts
    : shifts.filter((shift) => (shift.shift_type ?? 'work') === typeFilter)
  const nextSortOrder = shifts.reduce((max, shift) => Math.max(max, shift.sort_order), 0) + 1

  const toggleEnabled = async (shift: Shift) => {
    try {
      await updateMutation.mutateAsync({ id: shift.id, is_enabled: !shift.is_enabled })
      toast.success(t('scheduling.shifts.toast.saved', locale))
    } catch {
      toast.error(t('scheduling.shifts.toast.saveFailed', locale))
    }
  }

  const updateSortOrder = async (shift: Shift, sortOrder: number) => {
    try {
      await updateMutation.mutateAsync({ id: shift.id, sort_order: sortOrder })
      toast.success(t('scheduling.shifts.toast.saved', locale))
    } catch {
      toast.error(t('scheduling.shifts.toast.saveFailed', locale))
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast.success(t('scheduling.shifts.toast.deleted', locale))
      setDeleteTarget(null)
    } catch {
      toast.error(t('scheduling.shifts.toast.deleteFailed', locale))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-foreground">
            {t('scheduling.shifts.title', locale)}
          </h1>
          <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
            {(['all', 'work', 'leave'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setTypeFilter(type)}
                className={`h-7 rounded-md px-3 text-xs font-medium transition-colors ${
                  typeFilter === type
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t(`scheduling.shiftFilter.${type}`, locale)}
              </button>
            ))}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setForm({
            open: true,
            shift: null,
            defaultType: typeFilter === 'leave' ? 'leave' : 'work',
          })}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('scheduling.shifts.new', locale)}
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
          <div className="flex w-[100px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.color', locale)}
            </span>
          </div>
          <div className="flex min-w-0 flex-1 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.name', locale)}
            </span>
          </div>
          <div className="flex w-[110px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.type', locale)}
            </span>
          </div>
          <div className="flex w-[160px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.time', locale)}
            </span>
          </div>
          <div className="flex w-[88px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.sort', locale)}
            </span>
          </div>
          <div className="flex w-[100px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.status', locale)}
            </span>
          </div>
          <div className="flex w-[70px] shrink-0 items-center">
            <span className="text-sm font-semibold text-foreground/80">
              {t('scheduling.shifts.col.actions', locale)}
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="border-t border-border px-6 py-10 text-center text-sm text-muted-foreground">
            {t('scheduling.shifts.loading', locale)}
          </div>
        ) : visibleShifts.length === 0 ? (
          <div className="border-t border-border px-6 py-10 text-center text-sm text-muted-foreground">
            {t(
              typeFilter === 'leave'
                ? 'scheduling.shifts.emptyLeave'
                : typeFilter === 'work'
                  ? 'scheduling.shifts.emptyWork'
                  : 'scheduling.shifts.empty',
              locale,
            )}
          </div>
        ) : (
          visibleShifts.map((shift) => {
            const shiftType = shift.shift_type ?? 'work'
            const isLeave = shiftType === 'leave'
            const overnight = !isLeave && shift.end_time <= shift.start_time
            const hasReferences = shift.has_references ?? shift.has_assignments
            return (
              <div
                key={shift.id}
                className="flex h-14 items-center gap-6 border-t border-border px-6"
              >
                <div className="flex w-[100px] shrink-0 items-center">
                  <span
                    className="inline-flex h-7 items-center rounded-md px-2.5 text-xs font-medium text-white"
                    style={{ background: shift.color }}
                  >
                    {shift.name}
                  </span>
                </div>
                <div className="flex min-w-0 flex-1 items-center">
                  <span className="truncate text-sm text-foreground" title={shift.name}>
                    {shift.name}
                  </span>
                </div>
                <div className="flex w-[110px] shrink-0 items-center">
                  <span className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${
                    isLeave
                      ? 'bg-info/10 text-info'
                      : 'bg-muted text-muted-foreground'
                  }`}>
                    {isLeave && <IconCalendarOff size={13} />}
                    {t(`scheduling.shiftType.${shiftType}`, locale)}
                  </span>
                </div>
                <div className="flex w-[160px] shrink-0 items-center">
                  <span className="text-sm text-muted-foreground">
                    {isLeave
                      ? t('scheduling.shifts.allDay', locale)
                      : `${shift.start_time} - ${shift.end_time}`}
                    {overnight && (
                      <span className="text-amber-700">
                        {t('scheduling.shifts.overnightSuffix', locale)}
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex w-[88px] shrink-0 items-center">
                  <SortOrderCell
                    shift={shift}
                    disabled={updateMutation.isPending}
                    label={t('scheduling.shifts.col.sort', locale)}
                    onSave={(sortOrder) => updateSortOrder(shift, sortOrder)}
                  />
                </div>
                <div className="flex w-[100px] shrink-0 items-center">
                  <Switch
                    checked={shift.is_enabled}
                    onCheckedChange={() => toggleEnabled(shift)}
                    aria-label={t('scheduling.shifts.col.status', locale)}
                  />
                </div>
                <div className="flex w-[70px] shrink-0 items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setForm({ open: true, shift, defaultType: shiftType })}
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label={t('scheduling.shifts.edit', locale)}
                  >
                    <IconPencil size={18} />
                  </button>
                  {hasReferences ? (
                    <button
                      type="button"
                      disabled
                      className="cursor-not-allowed text-foreground/80 opacity-40"
                      title={t('scheduling.shifts.deleteDisabledTip', locale)}
                      aria-label={t('scheduling.shifts.delete', locale)}
                    >
                      <IconTrash size={18} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(shift)}
                      className="text-foreground/80 transition-colors hover:text-destructive"
                      aria-label={t('scheduling.shifts.delete', locale)}
                    >
                      <IconTrash size={18} />
                    </button>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      <ShiftFormDialog
        open={form.open}
        shift={form.shift}
        defaultType={form.defaultType}
        nextSortOrder={nextSortOrder}
        onClose={() => setForm({ open: false, shift: null, defaultType: 'work' })}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('scheduling.shifts.confirmDelete.title', locale)}
        message={t('scheduling.shifts.confirmDelete.message', locale)}
        itemName={deleteTarget?.name}
        confirmLabel={t('scheduling.shifts.confirmDelete.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        variant="destructive"
        loading={deleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
