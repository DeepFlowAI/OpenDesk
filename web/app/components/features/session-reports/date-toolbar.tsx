'use client'

import { IconCalendar, IconChevronDown, IconRefresh } from '@tabler/icons-react'
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

type Props = {
  start: string
  end: string
  asOf?: string | null
  loading?: boolean
  exportAction?: ReactNode
  onChange: (range: { start: string; end: string }) => void
  onRefresh: () => void
  onValidityChange?: (valid: boolean) => void
}

type PresetKey =
  | 'today'
  | 'yesterday'
  | 'last7Days'
  | 'last30Days'
  | 'thisWeek'
  | 'thisMonth'
  | 'last366Days'

type RangeErrorKey = 'startAfterEnd' | 'over366Days'

const PRESETS: { key: PresetKey; compute: () => { start: string; end: string } }[] = [
  {
    key: 'today',
    compute: () => {
      const d = isoDate(new Date())
      return { start: d, end: d }
    },
  },
  {
    key: 'yesterday',
    compute: () => {
      const t = new Date()
      t.setDate(t.getDate() - 1)
      const d = isoDate(t)
      return { start: d, end: d }
    },
  },
  {
    key: 'last7Days',
    compute: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 6)
      return { start: isoDate(start), end: isoDate(end) }
    },
  },
  {
    key: 'last30Days',
    compute: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 29)
      return { start: isoDate(start), end: isoDate(end) }
    },
  },
  {
    key: 'thisWeek',
    compute: () => {
      const today = new Date()
      // ISO week: Monday-anchored (matches backend bucket logic).
      const dow = (today.getDay() + 6) % 7
      const monday = new Date(today)
      monday.setDate(today.getDate() - dow)
      return { start: isoDate(monday), end: isoDate(today) }
    },
  },
  {
    key: 'thisMonth',
    compute: () => {
      const today = new Date()
      const first = new Date(today.getFullYear(), today.getMonth(), 1)
      return { start: isoDate(first), end: isoDate(today) }
    },
  },
  {
    key: 'last366Days',
    compute: () => {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 365)
      return { start: isoDate(start), end: isoDate(end) }
    },
  },
]

function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatAsOfTime(asOf?: string | null): string {
  if (!asOf) return '—'
  const d = new Date(asOf)
  if (isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function parseDateOnly(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null

  const [, y, m, d] = match
  return new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)))
}

function isOverMaxRange(start: string, end: string): boolean {
  const s = parseDateOnly(start)
  const e = parseDateOnly(end)
  if (!s || !e) return false

  const days = Math.floor((e.getTime() - s.getTime()) / 86_400_000) + 1
  return days > 366
}

function rangeErrorFor(start: string, end: string): RangeErrorKey | null {
  if (!start || !end) return null
  if (start > end) return 'startAfterEnd'
  if (isOverMaxRange(start, end)) return 'over366Days'
  return null
}

export function DateToolbar({
  start,
  end,
  asOf,
  loading,
  exportAction,
  onChange,
  onRefresh,
  onValidityChange,
}: Props) {
  const { locale } = useLocaleStore()
  const [localStart, setLocalStart] = useState(start)
  const [localEnd, setLocalEnd] = useState(end)
  const [rangeError, setRangeError] = useState<RangeErrorKey | null>(null)
  const lastSubmittedRange = useRef(`${start}:${end}`)

  useEffect(() => setLocalStart(start), [start])
  useEffect(() => setLocalEnd(end), [end])
  useEffect(() => {
    lastSubmittedRange.current = `${start}:${end}`
  }, [start, end])
  useEffect(() => {
    const error = rangeErrorFor(localStart, localEnd)
    setRangeError(error)
    onValidityChange?.(!error && !!localStart && !!localEnd)
  }, [localStart, localEnd, onValidityChange])

  const commit = (s: string, e: string) => {
    const error = rangeErrorFor(s, e)
    setRangeError(error)
    onValidityChange?.(!error && !!s && !!e)
    if (!s || !e || error) {
      return
    }
    const nextRange = `${s}:${e}`
    if ((s !== start || e !== end) && lastSubmittedRange.current !== nextRange) {
      lastSubmittedRange.current = nextRange
      onChange({ start: s, end: e })
    }
  }

  const handleStartValue = (nextStart: string) => {
    setLocalStart(nextStart)
    commit(nextStart, localEnd)
  }

  const handleEndValue = (nextEnd: string) => {
    setLocalEnd(nextEnd)
    commit(localStart, nextEnd)
  }

  const handlePresetRange = (range: { start: string; end: string }) => {
    setLocalStart(range.start)
    setLocalEnd(range.end)
    commit(range.start, range.end)
  }

  const activePreset = useMemo(
    () => PRESETS.find((p) => {
      const range = p.compute()
      return range.start === start && range.end === end
    })?.key,
    [start, end]
  )

  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="flex flex-col gap-1">
          {/* Date range input */}
          <div
            className={cn(
              'flex h-9 items-center gap-2 rounded-lg border bg-background px-3',
              rangeError ? 'border-red-300' : 'border-border'
            )}
          >
            <IconCalendar size={16} className="text-muted-foreground" />
            <input
              type="date"
              value={localStart}
              onInput={(e) => handleStartValue(e.currentTarget.value)}
              onChange={(e) => handleStartValue(e.target.value)}
              onBlur={() => commit(localStart, localEnd)}
              className="border-0 bg-transparent text-[13px] text-foreground outline-none"
              aria-label="Start date"
            />
            <span className="text-muted-foreground">~</span>
            <input
              type="date"
              value={localEnd}
              onInput={(e) => handleEndValue(e.currentTarget.value)}
              onChange={(e) => handleEndValue(e.target.value)}
              onBlur={() => commit(localStart, localEnd)}
              className="border-0 bg-transparent text-[13px] text-foreground outline-none"
              aria-label="End date"
            />
          </div>
          {rangeError && (
            <div className="text-xs text-red-600">
              {t(`ws.records.sessionReports.error.${rangeError}`, locale)}
            </div>
          )}
        </div>

        {/* Preset dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger className="flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground hover:bg-muted/50">
            {activePreset
              ? t(`ws.records.sessionReports.toolbar.preset.${activePreset}`, locale)
              : t('ws.records.sessionReports.toolbar.preset.custom', locale)}
            <IconChevronDown size={14} className="text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => commit(localStart, localEnd)}>
              {t('ws.records.sessionReports.toolbar.preset.custom', locale)}
            </DropdownMenuItem>
            {PRESETS.map((p) => (
              <DropdownMenuItem
                key={p.key}
                onClick={() => handlePresetRange(p.compute())}
              >
                {t(`ws.records.sessionReports.toolbar.preset.${p.key}`, locale)}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          aria-label={t('ws.records.sessionReports.toolbar.refresh', locale)}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background text-[#404040]',
            loading ? 'cursor-not-allowed opacity-50' : 'hover:bg-muted/50'
          )}
        >
          <IconRefresh size={16} className={loading ? 'animate-spin' : ''} />
        </button>
        <span className="text-xs text-muted-foreground">
          {t('ws.records.sessionReports.toolbar.lastUpdated', locale).replace(
            '{time}',
            formatAsOfTime(asOf)
          )}
        </span>
        {exportAction}
      </div>
    </div>
  )
}
