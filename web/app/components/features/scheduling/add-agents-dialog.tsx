'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { PoolMember, Shift } from '@/models/scheduling'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'

export type AddAgentsTarget =
  | { kind: 'cell'; shift: Shift; date: string; existingEmployeeIds: Set<number> }
  | { kind: 'batch'; cellCount: number; existingEmployeeIds: Set<number> }

export type AddAgentsDialogProps = {
  open: boolean
  target: AddAgentsTarget | null
  pool: PoolMember[]
  submitting: boolean
  dayLabel: (date: string) => string
  onClose: () => void
  onSubmit: (employeeIds: number[]) => void
}

export function AddAgentsDialog({
  open,
  target,
  pool,
  submitting,
  dayLabel,
  onClose,
  onSubmit,
}: AddAgentsDialogProps) {
  const { locale } = useLocaleStore()
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (open) {
      setQ('')
      setSelected(new Set())
    }
  }, [open])

  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase()
    if (!kw) return pool
    return pool.filter(
      (m) =>
        m.name.toLowerCase().includes(kw) ||
        (m.job_number ?? '').toLowerCase().includes(kw),
    )
  }, [pool, q])

  if (!target) return null

  const subtitle =
    target.kind === 'cell'
      ? t('scheduling.addAgents.subtitle', locale, {
          day: dayLabel(target.date),
          shift: target.shift.name,
        })
      : t('scheduling.addAgents.subtitleBatch', locale, { count: target.cellCount })

  const toggle = (id: number, disabled: boolean) => {
    if (disabled) return
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-[560px]"
      >
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle>{t('scheduling.addAgents.title', locale)}</DialogTitle>
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        </DialogHeader>

        <div className="space-y-3 px-5 py-4">
          <div className="relative">
            <IconSearch
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t('scheduling.addAgents.searchPlaceholder', locale)}
              className="pl-8"
            />
          </div>

          <div className="max-h-[320px] overflow-auto rounded-lg border border-border">
            {filtered.length === 0 ? (
              <div className="px-3 py-8 text-center text-xs text-muted-foreground">
                {t('scheduling.addAgents.empty', locale)}
              </div>
            ) : (
              filtered.map((member) => {
                const disabled = target.existingEmployeeIds.has(member.id)
                const checked = selected.has(member.id)
                return (
                  <button
                    key={member.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => toggle(member.id, disabled)}
                    className={`flex w-full items-center gap-3 border-b border-border px-3 py-2.5 text-left text-sm last:border-b-0 ${
                      disabled ? 'bg-muted/30 text-muted-foreground' : 'hover:bg-muted/40'
                    }`}
                  >
                    <Checkbox checked={checked} disabled={disabled} tabIndex={-1} />
                    <span className="flex-1 font-medium">{member.name}</span>
                    {member.job_number && (
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {member.job_number}
                      </span>
                    )}
                    {disabled && (
                      <span className="text-[11px] text-muted-foreground">
                        {t('scheduling.addAgents.inCell', locale)}
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>

          <p className="text-[11px] text-muted-foreground">
            {t('scheduling.addAgents.selectedHint', locale, { count: selected.size })}
          </p>
        </div>

        <DialogFooter className="px-5 py-4">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            {t('scheduling.form.cancel', locale)}
          </Button>
          <Button
            onClick={() => onSubmit([...selected])}
            disabled={submitting || selected.size === 0}
          >
            {t('scheduling.addAgents.submit', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
