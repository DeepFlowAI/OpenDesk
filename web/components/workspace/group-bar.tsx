'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { Locale } from '@/context/locale-store'
import type { UnifiedField } from '@/models/field-definition'
import type { ViewGroupItem } from '@/models/view-group'
import {
  EMPTY_GROUP_VALUE,
  buildSelectLookup,
  formatGroupLabel,
} from '@/lib/workspace-group'

type Props = {
  locale: Locale
  items: ViewGroupItem[]
  total: number
  /** undefined = "All", EMPTY_GROUP_VALUE = "Unassigned", otherwise raw string. */
  activeValue: string | undefined
  field: UnifiedField | null
  onChange: (value: string | undefined) => void
  isLoading?: boolean
}

export function GroupBar({
  locale,
  items,
  total,
  activeValue,
  field,
  onChange,
  isLoading,
}: Props) {
  const selectLookup = useMemo(() => buildSelectLookup(field), [field])

  if (isLoading) {
    return (
      <div className="px-5 pb-2.5">
        <div className="h-9 w-full animate-pulse rounded-md bg-accent/60" aria-hidden />
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto px-5 pb-2.5">
      <GroupChip
        label={locale === 'zh' ? '全部' : 'All'}
        count={total}
        active={activeValue === undefined}
        onClick={() => onChange(undefined)}
      />
      {items.map((it, idx) => {
        const isEmpty = it.value === null
        const value = isEmpty ? EMPTY_GROUP_VALUE : (it.value as string)
        const label = formatGroupLabel(it.value, field, selectLookup, locale)
        return (
          <GroupChip
            key={`${value}-${idx}`}
            label={label}
            count={it.count}
            active={activeValue === value}
            onClick={() => onChange(value)}
            muted={isEmpty}
          />
        )
      })}
    </div>
  )
}

function GroupChip({
  label,
  count,
  active,
  onClick,
  muted,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
  muted?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs transition-colors',
        active
          ? 'border-ring bg-info/10 text-primary'
          : 'border-border text-foreground/80 hover:bg-accent',
        muted && !active && 'text-muted-foreground',
      )}
    >
      <span className="max-w-[160px] truncate">{label}</span>
      <span
        className={cn(
          'rounded-md px-1.5 py-px text-[11px]',
          active ? 'bg-primary/10 text-primary' : 'bg-accent text-muted-foreground',
        )}
      >
        {count}
      </span>
    </button>
  )
}
