'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconCheck, IconChevronDown } from '@tabler/icons-react'

import type { TenantPhoneNumber } from '@/models/tenant-phone-number'
import { useTenantPhoneNumbers } from '@/service/use-tenant-phone-numbers'
import { cn } from '@/lib/utils'

type OutboundNumberSelectProps = {
  value: string
  onChange: (id: string, phoneNumber: string) => void
  disabled?: boolean
}

function normalizeTags(tags: string[] | undefined) {
  return (tags ?? []).map((tag) => tag.trim()).filter(Boolean)
}

function outboundNumberLabel(item: TenantPhoneNumber) {
  const tags = normalizeTags(item.tags)
  return tags.length > 0 ? `${item.phone_number} ${tags.join('、')}` : item.phone_number
}

function NumberTags({
  tags,
  maxVisible = 2,
  className,
}: {
  tags: string[] | undefined
  maxVisible?: number
  className?: string
}) {
  const normalized = normalizeTags(tags)
  if (normalized.length === 0) return null

  const visible = normalized.slice(0, maxVisible)
  const hiddenCount = normalized.length - visible.length

  return (
    <span className={cn('flex min-w-0 items-center gap-1', className)}>
      {visible.map((tag) => (
        <span
          key={tag}
          title={tag}
          className="inline-flex max-w-[84px] min-w-0 items-center rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium leading-4 text-muted-foreground"
        >
          <span className="truncate">{tag}</span>
        </span>
      ))}
      {hiddenCount > 0 ? (
        <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium leading-4 text-muted-foreground">
          +{hiddenCount}
        </span>
      ) : null}
    </span>
  )
}

export function OutboundNumberSelect({ value, onChange, disabled }: OutboundNumberSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const { data, isLoading } = useTenantPhoneNumbers({ page: 1, per_page: 100 })

  const outboundNumbers = useMemo(
    () => (data?.items ?? []).filter((item) => item.call_types.includes('outbound')),
    [data],
  )
  const selected = useMemo(
    () => outboundNumbers.find((item) => item.id === value),
    [outboundNumbers, value],
  )

  useEffect(() => {
    if (value || outboundNumbers.length === 0) return
    const first = outboundNumbers[0]
    onChange(first.id, first.phone_number)
  }, [value, outboundNumbers, onChange])

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (disabled) setOpen(false)
  }, [disabled])

  if (isLoading) {
    return (
      <button
        type="button"
        disabled
        className="h-10 w-[220px] rounded-lg border border-border bg-white px-3 text-left text-sm text-muted-foreground shadow-sm"
      >
        加载中...
      </button>
    )
  }

  if (outboundNumbers.length === 0) {
    return (
      <button
        type="button"
        disabled
        className="h-10 w-[220px] rounded-lg border border-border bg-white px-3 text-left text-sm text-muted-foreground shadow-sm"
      >
        无外呼号码
      </button>
    )
  }

  return (
    <div ref={rootRef} className="relative w-[220px]">
      <button
        type="button"
        onClick={() => {
          if (!disabled) setOpen((current) => !current)
        }}
        disabled={disabled}
        title={selected ? outboundNumberLabel(selected) : '外呼号码'}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-border bg-white px-3 text-sm shadow-sm outline-none transition focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="flex min-w-0 flex-1 items-center gap-2 text-left">
          {selected ? (
            <>
              <span className="min-w-[72px] truncate font-medium text-foreground">
                {selected.phone_number}
              </span>
              <NumberTags tags={selected.tags} maxVisible={1} />
            </>
          ) : (
            <span className="truncate text-muted-foreground">选择外呼号码</span>
          )}
        </span>
        <IconChevronDown
          size={16}
          className={cn(
            'shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {open && !disabled ? (
        <div
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 max-h-72 w-[280px] overflow-y-auto rounded-lg border border-border bg-white p-1.5 shadow-lg ring-1 ring-foreground/10"
        >
          {outboundNumbers.map((item) => {
            const active = item.id === value
            return (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(item.id, item.phone_number)
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors',
                  active ? 'bg-primary/10' : 'hover:bg-muted/80',
                )}
                title={outboundNumberLabel(item)}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">
                    {item.phone_number}
                  </span>
                  <NumberTags tags={item.tags} maxVisible={3} className="mt-1 flex-wrap" />
                </span>
                {active ? (
                  <IconCheck size={16} className="shrink-0 text-primary" />
                ) : (
                  <span className="h-4 w-4 shrink-0" />
                )}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
