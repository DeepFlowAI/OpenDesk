'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconCheck, IconSearch, IconUser, IconUsers, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useAddAssignments,
  useAssignableEmployees,
  useAssignableGroups,
} from '@/service/use-learning'

type PickerTab = 'group' | 'employee'

export function AddLearnersDialog({
  courseId,
  open,
  onClose,
}: {
  courseId: number
  open: boolean
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const [tab, setTab] = useState<PickerTab>('group')
  const [searchInput, setSearchInput] = useState('')
  const [q, setQ] = useState('')
  const [selectedGroups, setSelectedGroups] = useState<Set<number>>(new Set())
  const [selectedEmployees, setSelectedEmployees] = useState<Set<number>>(new Set())

  const groupsQuery = useAssignableGroups(courseId, '', open)
  const employeesQuery = useAssignableEmployees(courseId, { q: q || undefined, per_page: 100 }, open)
  const addAssignments = useAddAssignments(courseId)

  // Debounce the employee name search.
  useEffect(() => {
    const keyword = searchInput.trim()
    if (keyword === q) return
    const timer = setTimeout(() => setQ(keyword), 400)
    return () => clearTimeout(timer)
  }, [searchInput, q])

  useEffect(() => {
    if (open) return
    setTab('group')
    setSearchInput('')
    setQ('')
    setSelectedGroups(new Set())
    setSelectedEmployees(new Set())
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const groups = useMemo(() => groupsQuery.data?.items ?? [], [groupsQuery.data])
  const employees = useMemo(() => employeesQuery.data?.items ?? [], [employeesQuery.data])

  const toggle = (set: Set<number>, id: number): Set<number> => {
    const next = new Set(set)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }

  const selectedCount = selectedGroups.size + selectedEmployees.size

  const handleConfirm = async () => {
    const targets = [
      ...Array.from(selectedGroups).map((id) => ({ target_type: 'group' as const, target_id: id })),
      ...Array.from(selectedEmployees).map((id) => ({ target_type: 'employee' as const, target_id: id })),
    ]
    if (targets.length === 0) {
      onClose()
      return
    }
    try {
      const result = await addAssignments.mutateAsync(targets)
      toast.success(t('learning.toast.addedTargets', locale, { count: String(result.added_count) }))
      onClose()
    } catch {
      toast.error(t('learning.common.loadFailed', locale))
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="flex w-[560px] max-w-[92vw] flex-col rounded-xl bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold text-foreground">
            {t('learning.picker.title', locale)}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('learning.common.cancel', locale)}
            className="text-muted-foreground hover:text-foreground"
          >
            <IconX size={18} />
          </button>
        </div>

        <nav className="flex items-center gap-1 border-b border-border px-5">
          {(
            [
              { key: 'group', labelKey: 'learning.picker.byGroup' },
              { key: 'employee', labelKey: 'learning.picker.byEmployee' },
            ] as const
          ).map(({ key, labelKey }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`-mb-px flex h-10 items-center border-b-2 px-3 text-sm ${
                tab === key
                  ? 'border-primary font-semibold text-foreground'
                  : 'border-transparent text-muted-foreground'
              }`}
            >
              {t(labelKey, locale)}
            </button>
          ))}
        </nav>

        {tab === 'group' ? (
          <div className="max-h-72 min-h-40 overflow-y-auto px-2 py-2">
            {groupsQuery.isLoading ? (
              <p className="px-3 py-6 text-sm text-muted-foreground">
                {t('learning.common.loading', locale)}
              </p>
            ) : groups.length === 0 ? (
              <p className="px-3 py-6 text-sm text-muted-foreground">
                {t('learning.picker.empty', locale)}
              </p>
            ) : (
              groups.map((group) => {
                const disabled = group.added
                const checked = selectedGroups.has(group.id)
                return (
                  <button
                    key={group.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => setSelectedGroups((prev) => toggle(prev, group.id))}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm hover:bg-muted/50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                  >
                    <span
                      className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${
                        disabled
                          ? 'border-border bg-muted'
                          : checked
                            ? 'border-primary bg-primary text-white'
                            : 'border-border'
                      }`}
                    >
                      {!disabled && checked ? <IconCheck size={11} stroke={3} /> : null}
                    </span>
                    <IconUsers
                      size={15}
                      className={disabled ? 'text-muted-foreground/50' : 'text-sky-600'}
                    />
                    <span className={disabled ? 'text-muted-foreground/60' : 'font-medium'}>
                      {group.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {t('learning.picker.memberCount', locale, {
                        count: String(group.active_member_count),
                      })}
                    </span>
                    {disabled ? (
                      <span className="ml-auto text-xs text-muted-foreground/60">
                        {t('learning.picker.added', locale)}
                      </span>
                    ) : null}
                  </button>
                )
              })
            )}
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 px-5 py-3">
              <div className="flex h-9 flex-1 items-center gap-2 rounded-md border border-border px-3">
                <IconSearch size={16} className="text-muted-foreground" />
                <input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder={t('learning.picker.searchEmployee', locale)}
                  className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                />
              </div>
            </div>
            <div className="max-h-64 min-h-40 overflow-y-auto border-t border-border px-2 py-2">
              {employeesQuery.isLoading ? (
                <p className="px-3 py-6 text-sm text-muted-foreground">
                  {t('learning.common.loading', locale)}
                </p>
              ) : employees.length === 0 ? (
                <p className="px-3 py-6 text-sm text-muted-foreground">
                  {t('learning.picker.empty', locale)}
                </p>
              ) : (
                employees.map((employee) => {
                  const disabled = employee.assigned || employee.covered
                  const checked = selectedEmployees.has(employee.id)
                  return (
                    <button
                      key={employee.id}
                      type="button"
                      disabled={disabled}
                      onClick={() => setSelectedEmployees((prev) => toggle(prev, employee.id))}
                      className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm hover:bg-muted/50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                    >
                      <span
                        className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${
                          disabled
                            ? 'border-border bg-muted'
                            : checked
                              ? 'border-primary bg-primary text-white'
                              : 'border-border'
                        }`}
                      >
                        {!disabled && checked ? <IconCheck size={11} stroke={3} /> : null}
                      </span>
                      <IconUser
                        size={15}
                        className={disabled ? 'text-muted-foreground/50' : 'text-muted-foreground'}
                      />
                      <span className={disabled ? 'text-muted-foreground/60' : 'font-medium'}>
                        {employee.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {employee.group_names.join('、')}
                      </span>
                      {disabled ? (
                        <span className="ml-auto text-xs text-muted-foreground/60">
                          {t('learning.picker.assignedMark', locale)}
                        </span>
                      ) : null}
                    </button>
                  )
                })
              )}
            </div>
          </>
        )}

        <div className="flex items-center justify-between border-t border-border px-5 py-4">
          <span className="text-xs text-muted-foreground">
            {tab === 'group'
              ? t('learning.picker.selectedGroups', locale, { count: String(selectedGroups.size) })
              : t('learning.picker.selectedEmployees', locale, {
                  count: String(selectedEmployees.size),
                })}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="h-9 rounded-md border border-border px-4 text-sm"
            >
              {t('learning.common.cancel', locale)}
            </button>
            <button
              type="button"
              disabled={selectedCount === 0 || addAssignments.isPending}
              onClick={() => void handleConfirm()}
              className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {addAssignments.isPending ? '...' : t('learning.common.confirm', locale)}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
