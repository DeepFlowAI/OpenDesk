'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconDownload,
  IconFilter,
  IconRestore,
  IconSend,
  IconSparkles,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Button } from '@/components/ui/button'
import { PoolPicker } from './pool-picker'
import { PublishTag } from './publish-tag'
import type { PublishStatus } from '@/models/scheduling'
import {
  boardRangePreset,
  MAX_BOARD_RANGE_DAYS,
  type BoardRangePreset,
  type LayoutView,
} from './board-utils'

const LAYOUTS: LayoutView[] = ['shift-day', 'agent-day', 'calendar']
const PRESETS: BoardRangePreset[] = ['thisWeek', 'lastWeek', 'thisMonth', 'lastMonth']

export type BoardToolbarProps = {
  layout: LayoutView
  onLayoutChange: (layout: LayoutView) => void
  groupIds: number[]
  onGroupIdsChange: (ids: number[]) => void
  poolCount: number
  /** Board views: inclusive range. Calendar ignores these. */
  startDate: string
  endDate: string
  onRangeChange: (start: string, end: string) => void
  onRangeInvalid?: (reason: 'startAfterEnd' | 'overMaxDays') => void
  monthLabel: string
  onPrev: () => void
  onNext: () => void
  onPreset: (key: BoardRangePreset) => void
  onThisMonth: () => void
  multiMode: boolean
  onToggleMulti: () => void
  selectedCount: number
  onBatchAdd: () => void
  onBatchClear: () => void
  onCopyWeek: () => void
  onGenerate: () => void
  violationsOnly: boolean
  onToggleViolations: () => void
  violationCount?: number
  onExportExcel: () => void
  exportExcelDisabled?: boolean
  exporting?: boolean
  emptyPool: boolean
  /** Null/undefined: status unknown or query failed — tag and buttons stay hidden/disabled. */
  publishStatus?: PublishStatus | null
  publishing?: boolean
  resetting?: boolean
  onPublish: () => void
  onReset: () => void
}

function rangeError(
  start: string,
  end: string,
): 'startAfterEnd' | 'overMaxDays' | null {
  if (!start || !end) return null
  if (start > end) return 'startAfterEnd'
  const s = new Date(`${start}T00:00:00`)
  const e = new Date(`${end}T00:00:00`)
  const days = Math.floor((e.getTime() - s.getTime()) / 86_400_000) + 1
  if (days > MAX_BOARD_RANGE_DAYS) return 'overMaxDays'
  return null
}

export function BoardToolbar(props: BoardToolbarProps) {
  const { locale } = useLocaleStore()
  const isCalendar = props.layout === 'calendar'
  const isShiftDay = props.layout === 'shift-day'
  const [localStart, setLocalStart] = useState(props.startDate)
  const [localEnd, setLocalEnd] = useState(props.endDate)

  useEffect(() => setLocalStart(props.startDate), [props.startDate])
  useEffect(() => setLocalEnd(props.endDate), [props.endDate])

  const commitRange = (start: string, end: string, reportInvalid = false) => {
    const error = rangeError(start, end)
    if (error) {
      if (reportInvalid) {
        props.onRangeInvalid?.(error)
        setLocalStart(props.startDate)
        setLocalEnd(props.endDate)
      }
      return
    }
    if (start !== props.startDate || end !== props.endDate) {
      props.onRangeChange(start, end)
    }
  }

  const activePreset = useMemo(() => {
    return PRESETS.find((key) => {
      const range = boardRangePreset(key)
      return range.start === props.startDate && range.end === props.endDate
    })
  }, [props.startDate, props.endDate])

  const publishState = props.publishStatus?.state
  const publishResetTip = isCalendar
    ? t('scheduling.board.publishResetViewTip', locale)
    : undefined
  const resetDisabledReason = isCalendar
    ? publishResetTip
    : publishState === 'unpublished'
      ? t('scheduling.board.resetDisabledUnpublished', locale)
      : publishState === 'published'
        ? t('scheduling.board.resetDisabledClean', locale)
        : undefined

  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-border bg-white px-6 py-3">
      {/* Row 1: pool + business actions + publish lifecycle */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {t('scheduling.board.pool', locale)}
          </span>
          <PoolPicker groupIds={props.groupIds} onGroupIdsChange={props.onGroupIdsChange} />
          {!props.emptyPool && (
            <span className="text-xs text-muted-foreground">
              {t('scheduling.board.poolCount', locale, { count: props.poolCount })}
            </span>
          )}
        </div>

        <span className="h-5 w-px bg-border" />

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            disabled={props.emptyPool || isCalendar}
            title={isCalendar ? t('scheduling.board.generateDisabledTip', locale) : undefined}
            onClick={props.onGenerate}
          >
            <IconSparkles size={14} />
            {t('scheduling.board.generate', locale)}
          </Button>
          <Button
            variant="outline"
            disabled={props.emptyPool || isCalendar}
            title={isCalendar ? t('scheduling.board.copyWeekDisabledTip', locale) : undefined}
            onClick={props.onCopyWeek}
          >
            <IconCopy size={14} />
            {t('scheduling.board.copyWeek', locale)}
          </Button>
          <Button
            variant="outline"
            disabled={props.emptyPool || isCalendar}
            onClick={props.onToggleViolations}
            className={
              props.violationsOnly
                ? 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 hover:text-amber-900'
                : undefined
            }
          >
            <IconFilter size={14} />
            {t('scheduling.board.violationsFilter', locale)}
            {props.violationCount != null && props.violationCount > 0 && (
              <span className="rounded bg-amber-100 px-1 text-[10px] tabular-nums">
                {props.violationCount}
              </span>
            )}
          </Button>
          {!isCalendar && !props.emptyPool && (
            <Button
              variant={props.multiMode ? 'default' : 'outline'}
              onClick={props.onToggleMulti}
            >
              {props.multiMode
                ? t('scheduling.board.multiSelectOn', locale)
                : t('scheduling.board.multiSelect', locale)}
            </Button>
          )}
          {props.multiMode && (
            <>
              <span className="text-xs text-muted-foreground">
                {t('scheduling.board.selectedCount', locale, { count: props.selectedCount })}
              </span>
              <Button
                variant="outline"
                disabled={props.selectedCount === 0}
                onClick={props.onBatchAdd}
              >
                {isShiftDay
                  ? t('scheduling.board.batchAdd', locale)
                  : t('scheduling.board.batchPickShifts', locale)}
              </Button>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                disabled={props.selectedCount === 0}
                onClick={props.onBatchClear}
              >
                {t('scheduling.board.batchClear', locale)}
              </Button>
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {props.publishStatus && !isCalendar && <PublishTag status={props.publishStatus} />}
          <Button
            variant="outline"
            disabled={
              props.emptyPool || isCalendar || publishState !== 'dirty' || props.resetting
            }
            title={props.emptyPool ? undefined : resetDisabledReason}
            onClick={props.onReset}
          >
            <IconRestore size={14} />
            {t('scheduling.board.reset', locale)}
          </Button>
          <Button
            disabled={props.emptyPool || isCalendar || props.publishing}
            title={props.emptyPool ? undefined : publishResetTip}
            onClick={props.onPublish}
          >
            <IconSend size={14} />
            {t('scheduling.board.publish', locale)}
          </Button>
        </div>
      </div>

      {/* Row 2: view switch + date navigation + export */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {t('scheduling.board.layout.label', locale)}
          </span>
          <div className="inline-flex h-9 items-center rounded-md border border-border bg-muted/40 p-0.5">
            {LAYOUTS.map((layout) => (
              <button
                key={layout}
                type="button"
                onClick={() => props.onLayoutChange(layout)}
                className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                  props.layout === layout
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t(`scheduling.board.layout.${layout === 'shift-day' ? 'shiftDay' : layout === 'agent-day' ? 'agentDay' : 'calendar'}`, locale)}
              </button>
            ))}
          </div>
        </div>

        <span className="h-5 w-px bg-border" />

        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={props.onPrev}
            className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground hover:bg-muted"
          >
            <IconChevronLeft size={16} />
          </button>
          {isCalendar ? (
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm font-medium tabular-nums">
              {props.monthLabel}
            </div>
          ) : (
            <div className="flex h-9 items-center gap-1.5 rounded-md border border-border px-2 text-sm tabular-nums">
              <input
                type="date"
                value={localStart}
                onChange={(e) => {
                  const next = e.target.value
                  setLocalStart(next)
                  commitRange(next, localEnd)
                }}
                onBlur={() => commitRange(localStart, localEnd, true)}
                className="border-0 bg-transparent text-sm outline-none"
                aria-label={t('scheduling.board.rangeStart', locale)}
              />
              <span className="text-muted-foreground">-</span>
              <input
                type="date"
                value={localEnd}
                onChange={(e) => {
                  const next = e.target.value
                  setLocalEnd(next)
                  commitRange(localStart, next)
                }}
                onBlur={() => commitRange(localStart, localEnd, true)}
                className="border-0 bg-transparent text-sm outline-none"
                aria-label={t('scheduling.board.rangeEnd', locale)}
              />
            </div>
          )}
          <button
            type="button"
            onClick={props.onNext}
            className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground hover:bg-muted"
          >
            <IconChevronRight size={16} />
          </button>
          {isCalendar ? (
            <button
              type="button"
              onClick={props.onThisMonth}
              className="ml-1 h-9 rounded-md border border-border px-3 text-sm hover:bg-muted"
            >
              {t('scheduling.board.thisMonth', locale)}
            </button>
          ) : (
            <div className="ml-1 inline-flex h-9 items-center gap-0.5">
              {PRESETS.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => props.onPreset(key)}
                  className={`h-9 rounded-md border border-border px-2.5 text-sm transition-colors ${
                    activePreset === key
                      ? 'bg-primary/5 font-medium text-primary'
                      : 'text-foreground hover:bg-muted'
                  }`}
                >
                  {t(`scheduling.board.preset.${key}`, locale)}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            disabled={props.emptyPool || props.exportExcelDisabled || props.exporting}
            onClick={props.onExportExcel}
          >
            <IconDownload size={14} />
            {t('scheduling.board.exportExcel', locale)}
          </Button>
        </div>
      </div>
    </div>
  )
}
