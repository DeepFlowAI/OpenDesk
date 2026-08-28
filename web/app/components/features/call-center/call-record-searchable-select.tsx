'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconChevronDown, IconSearch, IconX } from '@tabler/icons-react'

import { cn } from '@/lib/utils'

export type CallRecordSelectOption = {
  value: string
  label: string
  description?: string
}

type Props = {
  value: string
  onChange: (value: string) => void
  options: CallRecordSelectOption[]
  placeholder: string
  searchPlaceholder: string
  emptyText: string
  className?: string
}

export function CallRecordSearchableSelect({
  value,
  onChange,
  options,
  placeholder,
  searchPlaceholder,
  emptyText,
  className,
}: Props) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = options.find((option) => option.value === value)
  const filtered = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase()
    if (!keyword) return options
    return options.filter((option) => (
      option.label.toLocaleLowerCase().includes(keyword)
      || option.description?.toLocaleLowerCase().includes(keyword)
    ))
  }, [options, search])

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  return (
    <div ref={rootRef} className={cn('relative min-w-[160px]', className)}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex h-9 w-full items-center gap-2 rounded-md border border-border bg-background px-2.5 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className={cn('min-w-0 flex-1 truncate', !selected && 'text-muted-foreground')}>
          {selected?.label ?? placeholder}
        </span>
        {value && (
          <span
            role="button"
            tabIndex={0}
            aria-label={placeholder}
            onClick={(event) => {
              event.stopPropagation()
              onChange('')
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') onChange('')
            }}
            className="text-muted-foreground hover:text-foreground"
          >
            <IconX size={14} />
          </span>
        )}
        <IconChevronDown size={14} className="shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute left-0 top-10 z-40 w-full min-w-[220px] rounded-md border border-border bg-popover p-2 shadow-lg">
          <div className="mb-2 flex h-8 items-center gap-1.5 rounded-md border border-border px-2">
            <IconSearch size={14} className="text-muted-foreground" />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={searchPlaceholder}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </div>
          <div role="listbox" className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-xs text-muted-foreground">{emptyText}</div>
            ) : filtered.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onClick={() => {
                  onChange(option.value)
                  setSearch('')
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full flex-col rounded-md px-2 py-2 text-left text-sm hover:bg-accent',
                  option.value === value && 'bg-accent',
                )}
              >
                <span className="text-foreground">{option.label}</span>
                {option.description && (
                  <span className="text-xs text-muted-foreground">{option.description}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
