'use client'

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconUsersGroup } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Assignment, PoolMember, Shift } from '@/models/scheduling'
import type { RuleViolation } from '@/models/scheduling-rule'
import {
  exportSchedulingAssignments,
  useAssignments,
  useCopyWeek,
  useCreateAssignments,
  useDeleteAssignments,
  usePoolMembers,
  usePublishStatus,
  usePublishWeek,
  useResetWeek,
  useShifts,
  useViolations,
} from '@/service/use-scheduling'
import { useRuleSets } from '@/service/use-scheduling-rules'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { BoardToolbar } from '@/app/components/features/scheduling/board-toolbar'
import { PoolPicker } from '@/app/components/features/scheduling/pool-picker'
import { ShiftDayGrid } from '@/app/components/features/scheduling/shift-day-grid'
import { AgentDayGrid } from '@/app/components/features/scheduling/agent-day-grid'
import { CalendarView } from '@/app/components/features/scheduling/calendar-view'
import { GenerateDialog } from '@/app/components/features/scheduling/generate-dialog'
import { ValidationDrawer } from '@/app/components/features/scheduling/validation-drawer'
import {
  HardBlockDialog,
  SoftWarnDialog,
} from '@/app/components/features/scheduling/rule-conflict-dialogs'
import {
  PublishDialog,
  ResetDialog,
} from '@/app/components/features/scheduling/publish-dialogs'
import { readRuleConflict } from '@/app/components/features/scheduling/read-rule-conflict'
import {
  agentCellViolations,
  shiftCellViolations,
} from '@/app/components/features/scheduling/violation-utils'
import {
  AddAgentsDialog,
  type AddAgentsTarget,
} from '@/app/components/features/scheduling/add-agents-dialog'
import {
  PickShiftsDialog,
  type PickShiftsTarget,
} from '@/app/components/features/scheduling/pick-shifts-dialog'
import { CopyWeekDialog } from '@/app/components/features/scheduling/copy-week-dialog'
import {
  addDays,
  assignmentsByAgentCell,
  assignmentsByCell,
  boardRangePreset,
  calendarRange,
  dateRange,
  dayCount,
  formatDate,
  MAX_BOARD_RANGE_DAYS,
  mondayOf,
  monthOf,
  parseDate,
  shiftDateRange,
  weekdayLabel,
  type BoardRangePreset,
  type LayoutView,
} from '@/app/components/features/scheduling/board-utils'

const LAYOUTS: LayoutView[] = ['shift-day', 'agent-day', 'calendar']

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function SchedulingBoardContent() {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const searchParams = useSearchParams()

  // ---------- URL state ----------
  const layoutParam = searchParams.get('layout') as LayoutView | null
  const layout: LayoutView = layoutParam && LAYOUTS.includes(layoutParam) ? layoutParam : 'shift-day'
  const startParam = searchParams.get('start')
  const endParam = searchParams.get('end')
  const weekParam = searchParams.get('week')
  const { startDate, endDate } = useMemo(() => {
    const isDate = (s: string | null) => !!s && /^\d{4}-\d{2}-\d{2}$/.test(s)
    if (isDate(startParam) && isDate(endParam) && startParam! <= endParam!) {
      const n = dayCount(startParam!, endParam!)
      if (n <= MAX_BOARD_RANGE_DAYS) {
        return { startDate: startParam!, endDate: endParam! }
      }
      return {
        startDate: startParam!,
        endDate: formatDate(addDays(parseDate(startParam!), MAX_BOARD_RANGE_DAYS - 1)),
      }
    }
    // Backward compatible: old ?week=YYYY-MM-DD (Monday of that week).
    if (isDate(weekParam)) {
      const start = formatDate(mondayOf(parseDate(weekParam!)))
      return { startDate: start, endDate: formatDate(addDays(parseDate(start), 6)) }
    }
    const fallback = boardRangePreset('thisWeek')
    return { startDate: fallback.start, endDate: fallback.end }
  }, [startParam, endParam, weekParam])
  const monthParam = searchParams.get('month')
  const month = monthParam && /^\d{4}-\d{2}$/.test(monthParam) ? monthParam : monthOf(new Date())
  const dayParam = searchParams.get('day')
  const selectedDay = dayParam && /^\d{4}-\d{2}-\d{2}$/.test(dayParam) ? dayParam : null
  const groupsParam = searchParams.get('groups') ?? ''
  const groupIds = useMemo(
    () =>
      groupsParam
        .split(',')
        .map((s) => Number(s))
        .filter((n) => Number.isInteger(n) && n > 0),
    [groupsParam],
  )
  const emptyPool = groupIds.length === 0
  const violationsOnly = searchParams.get('violations') === '1'

  const setParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString())
      for (const [key, value] of Object.entries(updates)) {
        if (value === null) params.delete(key)
        else params.set(key, value)
      }
      router.replace(`/scheduling/board?${params.toString()}`)
    },
    [router, searchParams],
  )

  const setBoardRange = useCallback(
    (start: string, end: string) => {
      setParams({ start, end, week: null })
    },
    [setParams],
  )

  // ---------- Local UI state ----------
  const [multiMode, setMultiMode] = useState(false)
  const [selectedCells, setSelectedCells] = useState<Set<string>>(new Set())
  const [addAgentsTarget, setAddAgentsTarget] = useState<AddAgentsTarget | null>(null)
  const [pickShiftsTarget, setPickShiftsTarget] = useState<PickShiftsTarget | null>(null)
  const [pickShiftsEmployeeId, setPickShiftsEmployeeId] = useState(0)
  const [copyWeekOpen, setCopyWeekOpen] = useState(false)
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const [hardBlock, setHardBlock] = useState<RuleViolation[] | null>(null)
  const [softWarn, setSoftWarn] = useState<{
    violations: RuleViolation[]
    retry: () => Promise<void>
  } | null>(null)
  const [softRetrying, setSoftRetrying] = useState(false)
  const [replacementConfirm, setReplacementConfirm] = useState<{
    affected: number
    retry: () => Promise<void>
  } | null>(null)
  const [replacementRetrying, setReplacementRetrying] = useState(false)

  // ---------- Data ----------
  const shiftsQuery = useShifts(!emptyPool)
  const enabledShifts = useMemo(
    () => (shiftsQuery.data?.items ?? []).filter((s) => s.is_enabled),
    [shiftsQuery.data],
  )
  const poolQuery = usePoolMembers(groupIds, !emptyPool)
  const pool = useMemo(() => poolQuery.data?.items ?? [], [poolQuery.data])
  const poolIds = useMemo(() => new Set(pool.map((m) => m.id)), [pool])

  const isCalendar = layout === 'calendar'
  const range = isCalendar
    ? calendarRange(month)
    : { start: startDate, end: endDate }
  const assignmentsQuery = useAssignments(range.start, range.end, !emptyPool)
  const assignments = useMemo(
    () => assignmentsQuery.data?.items ?? [],
    [assignmentsQuery.data],
  )
  const visibleShifts = useMemo(() => {
    const assignedShiftIds = new Set(assignments.map((assignment) => assignment.shift.id))
    return (shiftsQuery.data?.items ?? []).filter(
      (shift) => shift.is_enabled || assignedShiftIds.has(shift.id),
    )
  }, [assignments, shiftsQuery.data])

  const createMutation = useCreateAssignments()
  const deleteMutation = useDeleteAssignments()
  const copyWeekMutation = useCopyWeek()
  const publishMutation = usePublishWeek()
  const resetMutation = useResetWeek()
  const publishStatusQuery = usePublishStatus(startDate, !emptyPool && !isCalendar)

  // Rule-based validation: draft checks use the tenant default rule set.
  const ruleSetsQuery = useRuleSets(!emptyPool)
  const defaultRuleSet = useMemo(
    () => (ruleSetsQuery.data?.items ?? []).find((rs) => rs.is_default) ?? null,
    [ruleSetsQuery.data],
  )
  const violationsQuery = useViolations(range.start, range.end, groupIds, !emptyPool && !isCalendar)
  const violations = useMemo(() => violationsQuery.data?.items ?? [], [violationsQuery.data])
  const shiftViolationCells = useMemo(
    () => shiftCellViolations(violations, assignments),
    [violations, assignments],
  )
  const agentViolationCells = useMemo(() => agentCellViolations(violations), [violations])

  const boardDays = useMemo(() => dateRange(startDate, endDate), [startDate, endDate])
  /** Target week Monday for "copy last week" (uses the Monday of the range start). */
  const weekStart = formatDate(mondayOf(parseDate(startDate)))
  const byCell = useMemo(() => assignmentsByCell(assignments), [assignments])
  const byAgentCell = useMemo(() => assignmentsByAgentCell(assignments), [assignments])

  const dayLabel = useCallback(
    (date: string) => {
      const d = parseDate(date)
      return `${weekdayLabel(date, locale)} ${d.getMonth() + 1}/${d.getDate()}`
    },
    [locale],
  )

  // Reset multi-select when leaving week views or changing pool/range.
  useEffect(() => {
    setMultiMode(false)
    setSelectedCells(new Set())
  }, [layout, startDate, endDate, groupsParam])

  useEffect(() => {
    if (!multiMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMultiMode(false)
        setSelectedCells(new Set())
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [multiMode])

  // ---------- Mutations helpers ----------
  const opFailed = () => toast.error(t('scheduling.board.toast.opFailed', locale))

  /**
   * Run a schedule write with rule validation: hard violations open the block
   * dialog; soft violations open a confirm that retries with allow_soft.
   */
  const runWithRuleCheck = async (
    fn: (allowSoft: boolean, replaceConflicts: boolean) => Promise<void>,
    allowSoft = false,
    replaceConflicts = false,
  ) => {
    try {
      await fn(allowSoft, replaceConflicts)
    } catch (err) {
      const conflict = await readRuleConflict(err)
      if (!conflict) {
        opFailed()
        return
      }
      if (conflict.code === 'LEAVE_WORK_CONFLICT') {
        setReplacementConfirm({
          affected: conflict.affectedEmployeeDates,
          retry: () => runWithRuleCheck(fn, allowSoft, true),
        })
      } else if (conflict.code === 'RULE_HARD_VIOLATION') {
        setHardBlock(conflict.violations)
      } else {
        setSoftWarn({
          violations: conflict.violations,
          retry: () => runWithRuleCheck(fn, true, replaceConflicts),
        })
      }
    }
  }

  const confirmReplacement = async () => {
    if (!replacementConfirm) return
    const retry = replacementConfirm.retry
    setReplacementRetrying(true)
    setReplacementConfirm(null)
    try {
      await retry()
    } finally {
      setReplacementRetrying(false)
    }
  }

  const confirmSoftWarn = async () => {
    if (!softWarn) return
    setSoftRetrying(true)
    try {
      await softWarn.retry()
      setSoftWarn(null)
    } catch {
      opFailed()
      setSoftWarn(null)
    } finally {
      setSoftRetrying(false)
    }
  }

  const removeAssignment = async (assignment: Assignment) => {
    try {
      await deleteMutation.mutateAsync([assignment.id])
      toast.success(t('scheduling.addAgents.toast.removed', locale))
    } catch {
      opFailed()
    }
  }

  const submitAddAgents = async (employeeIds: number[]) => {
    if (!addAgentsTarget || employeeIds.length === 0) return
    let items: { employee_id: number; shift_id: number; date: string }[]
    if (addAgentsTarget.kind === 'cell') {
      const { shift, date } = addAgentsTarget
      items = employeeIds.map((employee_id) => ({
        employee_id,
        shift_id: shift.id,
        date,
      }))
    } else {
      items = [...selectedCells].flatMap((key) => {
        const sep = key.indexOf(':')
        const shiftId = Number(key.slice(0, sep))
        const date = key.slice(sep + 1)
        return employeeIds.map((employee_id) => ({
          employee_id,
          shift_id: shiftId,
          date,
        }))
      })
    }
    const requestedTypes = new Map<string, Set<string>>()
    const requestedShiftIds = new Map<string, Set<number>>()
    const shiftMap = new Map(enabledShifts.map((shift) => [shift.id, shift]))
    for (const item of items) {
      const key = `${item.employee_id}:${item.date}`
      const types = requestedTypes.get(key) ?? new Set<string>()
      types.add(shiftMap.get(item.shift_id)?.shift_type ?? 'work')
      requestedTypes.set(key, types)
      const ids = requestedShiftIds.get(key) ?? new Set<number>()
      ids.add(item.shift_id)
      requestedShiftIds.set(key, ids)
    }
    if (
      [...requestedTypes.entries()].some(([key, types]) => {
        const leaveCount = [...(requestedShiftIds.get(key) ?? [])].filter(
          (shiftId) => shiftMap.get(shiftId)?.shift_type === 'leave',
        ).length
        return types.size > 1 || leaveCount > 1
      })
    ) {
      toast.error(t('scheduling.board.leaveConflict.mixedSelection', locale))
      return
    }
    await runWithRuleCheck(async (allowSoft, replaceConflicts) => {
      const res = await createMutation.mutateAsync({
        group_ids: groupIds,
        items,
        allow_soft: allowSoft,
        replace_conflicts: replaceConflicts,
      })
      toast.success(t('scheduling.addAgents.toast.added', locale, { count: res.created }))
      setAddAgentsTarget(null)
      setSelectedCells(new Set())
    })
  }

  const submitPickShifts = async (selectedShiftIds: number[]) => {
    if (!pickShiftsTarget) return
    await runWithRuleCheck(async (allowSoft, replaceConflicts) => {
      if (pickShiftsTarget.kind === 'cell') {
        const { date, currentShiftIds } = pickShiftsTarget
        const next = new Set(selectedShiftIds)
        const createItems = [...next]
          .filter((id) => !currentShiftIds.has(id))
          .map((shift_id) => ({ employee_id: pickShiftsEmployeeId, shift_id, date }))
        const removeIds = (byAgentCell.get(`${pickShiftsEmployeeId}:${date}`) ?? [])
          .filter((a) => {
            if (next.size === 0) return true
            const nextType =
              enabledShifts.find((shift) => next.has(shift.id))?.shift_type ?? 'work'
            const currentType = a.shift.shift_type ?? 'work'
            return currentType === nextType && !next.has(a.shift.id)
          })
          .map((a) => a.id)
        if (createItems.length > 0) {
          await createMutation.mutateAsync({
            group_ids: groupIds,
            items: createItems,
            allow_soft: allowSoft,
            replace_conflicts: replaceConflicts,
          })
        }
        if (removeIds.length > 0) {
          await deleteMutation.mutateAsync(removeIds)
        }
      } else {
        const items = [...selectedCells].flatMap((key) => {
          const sep = key.indexOf(':')
          const employeeId = Number(key.slice(0, sep))
          const date = key.slice(sep + 1)
          return selectedShiftIds.map((shift_id) => ({
            employee_id: employeeId,
            shift_id,
            date,
          }))
        })
        if (items.length > 0) {
          await createMutation.mutateAsync({
            group_ids: groupIds,
            items,
            allow_soft: allowSoft,
            replace_conflicts: replaceConflicts,
          })
        }
        setSelectedCells(new Set())
      }
      toast.success(t('scheduling.pickShifts.toast.saved', locale))
      setPickShiftsTarget(null)
    })
  }

  const submitCopyWeek = async (mode: 'skip' | 'overwrite') => {
    await runWithRuleCheck(async (allowSoft) => {
      const result = await copyWeekMutation.mutateAsync({
        week_start: weekStart,
        mode,
        group_ids: groupIds,
        allow_soft: allowSoft,
      })
      toast.success(
        result.skipped_leave_conflicts > 0
          ? t('scheduling.copyWeek.toastWithLeaveSkipped', locale, {
              count: result.skipped_leave_conflicts,
            })
          : t('scheduling.copyWeek.toast', locale),
      )
      setCopyWeekOpen(false)
    })
  }

  const confirmPublish = async () => {
    try {
      await publishMutation.mutateAsync(startDate)
      toast.success(t('scheduling.board.publishSuccess', locale))
      setPublishOpen(false)
    } catch {
      opFailed()
    }
  }

  const confirmReset = async () => {
    try {
      await resetMutation.mutateAsync(startDate)
      toast.success(t('scheduling.board.resetSuccess', locale))
      setResetOpen(false)
    } catch {
      opFailed()
      setResetOpen(false)
    }
  }

  const clearSelectedCells = async () => {
    const ids: number[] = []
    for (const key of selectedCells) {
      const list = (layout === 'shift-day' ? byCell : byAgentCell).get(key) ?? []
      ids.push(...list.map((a) => a.id))
    }
    try {
      if (ids.length > 0) await deleteMutation.mutateAsync(ids)
      toast.success(t('scheduling.board.toast.cleared', locale))
      setClearConfirmOpen(false)
      setSelectedCells(new Set())
    } catch {
      opFailed()
    }
  }

  // ---------- Cell interactions ----------
  const toggleCell = (key: string) => {
    setSelectedCells((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const onShiftCellClick = (shift: Shift, date: string) => {
    if (multiMode) {
      toggleCell(`${shift.id}:${date}`)
      return
    }
    if (!shift.is_enabled) return
    const existing = new Set(
      (byCell.get(`${shift.id}:${date}`) ?? []).map((a) => a.employee.id),
    )
    setAddAgentsTarget({ kind: 'cell', shift, date, existingEmployeeIds: existing })
  }

  const onAgentCellClick = (member: PoolMember, date: string) => {
    if (multiMode) {
      toggleCell(`${member.id}:${date}`)
      return
    }
    const current = new Set(
      (byAgentCell.get(`${member.id}:${date}`) ?? []).map((a) => a.shift.id),
    )
    setPickShiftsEmployeeId(member.id)
    setPickShiftsTarget({
      kind: 'cell',
      employeeName: member.name,
      date,
      currentShiftIds: current,
    })
  }

  const onBatchAdd = () => {
    if (selectedCells.size === 0) return
    if (layout === 'shift-day') {
      if (
        [...selectedCells].some((key) => {
          const shiftId = Number(key.slice(0, key.indexOf(':')))
          return !enabledShifts.some((shift) => shift.id === shiftId)
        })
      ) {
        toast.error(t('scheduling.board.disabledSelection', locale))
        return
      }
      // Union of employees already in any selected cell: disabled in picker.
      const existing = new Set<number>()
      for (const key of selectedCells) {
        for (const a of byCell.get(key) ?? []) existing.add(a.employee.id)
      }
      setAddAgentsTarget({
        kind: 'batch',
        cellCount: selectedCells.size,
        existingEmployeeIds: existing,
      })
    } else if (layout === 'agent-day') {
      setPickShiftsTarget({ kind: 'batch', cellCount: selectedCells.size })
    }
  }

  // ---------- Toolbar handlers ----------
  const navPrev = () => {
    if (isCalendar) {
      const d = parseDate(`${month}-01`)
      setParams({ month: monthOf(new Date(d.getFullYear(), d.getMonth() - 1, 1)), day: null })
    } else {
      const next = shiftDateRange(startDate, endDate, -1)
      setBoardRange(next.start, next.end)
    }
  }
  const navNext = () => {
    if (isCalendar) {
      const d = parseDate(`${month}-01`)
      setParams({ month: monthOf(new Date(d.getFullYear(), d.getMonth() + 1, 1)), day: null })
    } else {
      const next = shiftDateRange(startDate, endDate, 1)
      setBoardRange(next.start, next.end)
    }
  }
  const applyPreset = (key: BoardRangePreset) => {
    const next = boardRangePreset(key)
    setBoardRange(next.start, next.end)
  }
  const navThisMonth = () => {
    setParams({ month: monthOf(new Date()), day: null })
  }

  const onRangeInvalid = (reason: 'startAfterEnd' | 'overMaxDays') => {
    toast.error(
      reason === 'overMaxDays'
        ? t('scheduling.board.rangeError.overMaxDays', locale, { max: MAX_BOARD_RANGE_DAYS })
        : t('scheduling.board.rangeError.startAfterEnd', locale),
    )
  }

  const exportExcel = async () => {
    // Board views export the selected range; the calendar exports the natural month.
    let start = range.start
    let end = range.end
    if (isCalendar) {
      const [y, m] = month.split('-').map(Number)
      start = `${month}-01`
      end = formatDate(new Date(y, m, 0))
    }
    setExporting(true)
    try {
      const result = await exportSchedulingAssignments({
        startDate: start,
        endDate: end,
        groupIds,
      })
      triggerDownload(result.blob, result.filename)
      toast.success(t('scheduling.board.toast.exported', locale))
    } catch {
      toast.error(t('scheduling.board.toast.exportFailed', locale))
    } finally {
      setExporting(false)
    }
  }

  const loading = shiftsQuery.isLoading || poolQuery.isLoading || assignmentsQuery.isLoading

  // ---------- Render ----------
  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <BoardToolbar
        layout={layout}
        onLayoutChange={(next) => setParams({ layout: next === 'shift-day' ? null : next })}
        groupIds={groupIds}
        onGroupIdsChange={(ids) => setParams({ groups: ids.length > 0 ? ids.join(',') : null })}
        poolCount={pool.length}
        startDate={startDate}
        endDate={endDate}
        onRangeChange={setBoardRange}
        onRangeInvalid={onRangeInvalid}
        monthLabel={month}
        onPrev={navPrev}
        onNext={navNext}
        onPreset={applyPreset}
        onThisMonth={navThisMonth}
        multiMode={multiMode}
        onToggleMulti={() => {
          setMultiMode((v) => !v)
          setSelectedCells(new Set())
        }}
        selectedCount={selectedCells.size}
        onBatchAdd={onBatchAdd}
        onBatchClear={() => setClearConfirmOpen(true)}
        onCopyWeek={() => setCopyWeekOpen(true)}
        onGenerate={() => setGenerateOpen(true)}
        violationsOnly={violationsOnly}
        onToggleViolations={() => setParams({ violations: violationsOnly ? null : '1' })}
        violationCount={violations.length}
        onExportExcel={exportExcel}
        exporting={exporting}
        emptyPool={emptyPool}
        publishStatus={publishStatusQuery.data ?? null}
        publishing={publishMutation.isPending}
        resetting={resetMutation.isPending}
        onPublish={() => setPublishOpen(true)}
        onReset={() => setResetOpen(true)}
      />

      {emptyPool ? (
        <EmptyPoolGuide
          groupIds={groupIds}
          onGroupIdsChange={(ids) =>
            setParams({ groups: ids.length > 0 ? ids.join(',') : null })
          }
        />
      ) : visibleShifts.length === 0 && !shiftsQuery.isLoading ? (
        <div className="flex min-h-0 flex-1 items-center justify-center bg-muted/20 px-8">
          <div className="flex w-[420px] flex-col items-center gap-3 rounded-xl border border-border bg-white p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">
              {t('scheduling.board.noEnabledShifts', locale)}
            </p>
            <Link href="/scheduling/shifts">
              <Button>{t('scheduling.board.goShifts', locale)}</Button>
            </Link>
          </div>
        </div>
      ) : loading ? (
        <div className="flex min-h-0 flex-1 items-center justify-center text-xs text-muted-foreground">
          {t('scheduling.board.loading', locale)}
        </div>
      ) : layout === 'agent-day' ? (
        <AgentDayGrid
          weekDates={boardDays}
          shifts={visibleShifts}
          assignments={assignments}
          pool={pool}
          multiMode={multiMode}
          selectedCells={selectedCells}
          onCellClick={onAgentCellClick}
          onRemove={removeAssignment}
          violationCells={agentViolationCells}
          violationsOnly={violationsOnly}
          targets={
            defaultRuleSet?.targets_enabled !== false ? (defaultRuleSet?.targets ?? null) : null
          }
        />
      ) : layout === 'calendar' ? (
        <CalendarView
          month={month}
          selectedDay={selectedDay}
          shifts={visibleShifts}
          assignments={assignments}
          poolIds={poolIds}
          onSelectDay={(date) => setParams({ day: date })}
          onAddAgents={(shift, date) => {
            const existing = new Set(
              (byCell.get(`${shift.id}:${date}`) ?? []).map((a) => a.employee.id),
            )
            setAddAgentsTarget({ kind: 'cell', shift, date, existingEmployeeIds: existing })
          }}
          onRemove={removeAssignment}
        />
      ) : (
        <ShiftDayGrid
          weekDates={boardDays}
          shifts={visibleShifts}
          assignments={assignments}
          poolIds={poolIds}
          multiMode={multiMode}
          selectedCells={selectedCells}
          onCellClick={onShiftCellClick}
          onRemove={removeAssignment}
          violationCells={shiftViolationCells}
          violationsOnly={violationsOnly}
          targets={
            defaultRuleSet?.targets_enabled !== false ? (defaultRuleSet?.targets ?? null) : null
          }
        />
      )}

      <ValidationDrawer
        open={violationsOnly && !emptyPool && !isCalendar}
        items={violations}
        hardCount={violationsQuery.data?.hard_count ?? 0}
        softCount={violationsQuery.data?.soft_count ?? 0}
        onClose={() => setParams({ violations: null })}
      />

      <AddAgentsDialog
        open={addAgentsTarget !== null}
        target={addAgentsTarget}
        pool={pool}
        submitting={createMutation.isPending}
        dayLabel={dayLabel}
        onClose={() => setAddAgentsTarget(null)}
        onSubmit={submitAddAgents}
      />
      <PickShiftsDialog
        open={pickShiftsTarget !== null}
        target={pickShiftsTarget}
        shifts={enabledShifts}
        submitting={createMutation.isPending || deleteMutation.isPending}
        dayLabel={dayLabel}
        onClose={() => setPickShiftsTarget(null)}
        onSubmit={submitPickShifts}
      />
      <CopyWeekDialog
        open={copyWeekOpen}
        submitting={copyWeekMutation.isPending}
        onClose={() => setCopyWeekOpen(false)}
        onSubmit={submitCopyWeek}
      />
      <GenerateDialog
        open={generateOpen}
        groupIds={groupIds}
        startDate={startDate}
        endDate={endDate}
        shifts={enabledShifts.filter((shift) => (shift.shift_type ?? 'work') === 'work')}
        onClose={() => setGenerateOpen(false)}
        onApplied={() => setGenerateOpen(false)}
      />
      <HardBlockDialog
        open={hardBlock !== null}
        violations={hardBlock ?? []}
        onClose={() => setHardBlock(null)}
      />
      <PublishDialog
        open={publishOpen}
        hardViolations={violations.filter((v) => v.level === 'hard')}
        submitting={publishMutation.isPending}
        onCancel={() => setPublishOpen(false)}
        onConfirm={confirmPublish}
      />
      <ResetDialog
        open={resetOpen}
        submitting={resetMutation.isPending}
        onCancel={() => setResetOpen(false)}
        onConfirm={confirmReset}
      />
      <SoftWarnDialog
        open={softWarn !== null}
        violations={softWarn?.violations ?? []}
        submitting={softRetrying}
        onCancel={() => setSoftWarn(null)}
        onConfirm={confirmSoftWarn}
      />
      <ConfirmDialog
        open={replacementConfirm !== null}
        title={t('scheduling.board.leaveConflict.title', locale)}
        message={t('scheduling.board.leaveConflict.message', locale, {
          count: replacementConfirm?.affected ?? 0,
        })}
        confirmLabel={t('scheduling.board.leaveConflict.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        loading={replacementRetrying}
        onCancel={() => setReplacementConfirm(null)}
        onConfirm={confirmReplacement}
      />
      <ConfirmDialog
        open={clearConfirmOpen}
        title={t('scheduling.board.clearConfirm.title', locale)}
        message={t('scheduling.board.clearConfirm.message', locale, {
          count: selectedCells.size,
        })}
        confirmLabel={t('scheduling.board.clearConfirm.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        variant="destructive"
        loading={deleteMutation.isPending}
        onCancel={() => setClearConfirmOpen(false)}
        onConfirm={clearSelectedCells}
      />
    </div>
  )
}

function EmptyPoolGuide({
  groupIds,
  onGroupIdsChange,
}: {
  groupIds: number[]
  onGroupIdsChange: (ids: number[]) => void
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-muted/20 px-8">
      <div className="w-[420px] rounded-xl border border-border bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <IconUsersGroup size={24} />
        </div>
        <h2 className="text-base font-semibold">
          {t('scheduling.board.emptyPool.title', locale)}
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {t('scheduling.board.emptyPool.desc', locale)}
        </p>
        <div className="mt-5 flex justify-center">
          <PoolPicker
            groupIds={groupIds}
            onGroupIdsChange={onGroupIdsChange}
            trigger={
              <button
                type="button"
                className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
              >
                {t('scheduling.board.emptyPool.cta', locale)}
              </button>
            }
          />
        </div>
      </div>
    </div>
  )
}

export default function SchedulingBoardPage() {
  return (
    <Suspense>
      <SchedulingBoardContent />
    </Suspense>
  )
}
