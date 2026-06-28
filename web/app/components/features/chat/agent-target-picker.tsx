'use client'

import { IconLoader2, IconSearch } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type AgentTargetStatus = 'online' | 'busy' | 'offline'

export type AgentTargetPickerItem = {
  id: number
  displayName: string
  avatar: string | null
  jobNumber?: string | null
  onlineStatus: AgentTargetStatus
  currentCount?: number
  maxConcurrent?: number
  available: boolean
  disabledText?: string | null
}

type AgentTargetPickerProps = {
  keyword: string
  onKeywordChange: (value: string) => void
  searchPlaceholder: string
  isLoading: boolean
  isFetching: boolean
  items: AgentTargetPickerItem[]
  selectedId: number | null
  onSelect: (item: AgentTargetPickerItem) => void
  emptyText: string
  statusLabel: (status: AgentTargetStatus) => string
  feedback?: ReactNode
  className?: string
  listMinHeightClassName?: string
  autoFocus?: boolean
}

const STATUS_DOT_CLASS: Record<AgentTargetStatus, string> = {
  online: 'bg-emerald-500',
  busy: 'bg-amber-500',
  offline: 'bg-gray-400',
}

function initialOf(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?'
}

export function AgentTargetPicker({
  keyword,
  onKeywordChange,
  searchPlaceholder,
  isLoading,
  isFetching,
  items,
  selectedId,
  onSelect,
  emptyText,
  statusLabel,
  feedback,
  className,
  listMinHeightClassName = 'min-h-[220px]',
  autoFocus = true,
}: AgentTargetPickerProps) {
  return (
    <div className={cn('space-y-3', className)}>
      <div className="relative">
        <IconSearch size={16} stroke={1.5} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          placeholder={searchPlaceholder}
          className="pl-8 pr-8"
          autoFocus={autoFocus}
        />
        {isFetching && (
          <IconLoader2 size={16} className="absolute right-2.5 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      {feedback}

      <div className={cn('-mx-1 max-h-[360px] overflow-y-auto px-1', listMinHeightClassName)}>
        {isLoading ? (
          <div className="space-y-2 py-2">
            {[0, 1, 2].map((item) => (
              <div key={item} className="h-12 animate-pulse rounded-md bg-muted/60" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className={cn('flex h-full items-center justify-center text-sm text-muted-foreground', listMinHeightClassName)}>{emptyText}</div>
        ) : (
          <ul className="divide-y divide-border/60">
            {items.map((item) => {
              const selected = selectedId === item.id
              const hasCapacity = item.currentCount !== undefined && item.maxConcurrent !== undefined

              return (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={!item.available}
                    onClick={() => onSelect(item)}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors',
                      item.available ? 'cursor-pointer hover:bg-muted' : 'cursor-not-allowed opacity-60',
                      selected && 'bg-primary/10 hover:bg-primary/10',
                    )}
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-sm font-medium text-foreground">
                      {item.avatar ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={item.avatar} alt={item.displayName} className="h-full w-full object-cover" />
                      ) : (
                        initialOf(item.displayName)
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-foreground">{item.displayName}</span>
                      <span className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                        <span className={cn('h-2 w-2 shrink-0 rounded-full', STATUS_DOT_CLASS[item.onlineStatus])} />
                        <span className="shrink-0">{statusLabel(item.onlineStatus)}</span>
                        {hasCapacity && (
                          <span className="shrink-0">
                            {item.currentCount}/{item.maxConcurrent}
                          </span>
                        )}
                        {item.jobNumber && <span className="truncate">{item.jobNumber}</span>}
                      </span>
                    </span>
                    {item.disabledText && (
                      <span className="shrink-0 text-xs text-muted-foreground">{item.disabledText}</span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
