'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconChevronDown, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import {
  useFieldReferenceEmployeeGroup,
  useFieldReferenceEmployeeGroups,
  type FieldReferenceEmployeeGroupOption,
} from '@/service/use-field-reference-options'

type EmployeeGroupSelectProps = {
  value: number | number[] | null | undefined
  onChange: (value: number | number[] | null) => void
  multi?: boolean
  disabled?: boolean
  placeholder?: string
  memberId?: number | null
  className?: string
  dropdownPlacement?: 'top' | 'bottom'
  autoFocus?: boolean
}

function groupDisplayName(group: FieldReferenceEmployeeGroupOption | undefined, fallbackId?: number): string {
  if (!group) return fallbackId ? `Group #${fallbackId}` : ''
  return group.description ? `${group.name} · ${group.description}` : group.name
}

function getDropdownPlacement(root: HTMLElement | null, expectedHeight = 256): 'top' | 'bottom' {
  if (!root || typeof window === 'undefined') return 'bottom'
  const rect = root.getBoundingClientRect()
  let boundaryTop = 0
  let boundaryBottom = window.innerHeight

  let parent = root.parentElement
  while (parent) {
    const style = window.getComputedStyle(parent)
    if (/(auto|scroll|hidden)/.test(style.overflowY)) {
      const parentRect = parent.getBoundingClientRect()
      boundaryTop = Math.max(boundaryTop, parentRect.top)
      boundaryBottom = Math.min(boundaryBottom, parentRect.bottom)
      break
    }
    parent = parent.parentElement
  }

  const spaceBelow = boundaryBottom - rect.bottom
  const spaceAbove = rect.top - boundaryTop
  return spaceBelow < expectedHeight && spaceAbove > spaceBelow ? 'top' : 'bottom'
}

export function EmployeeGroupSelect({
  value,
  onChange,
  multi = false,
  disabled = false,
  placeholder = 'Search groups...',
  memberId,
  className,
  dropdownPlacement,
  autoFocus = false,
}: EmployeeGroupSelectProps) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!autoFocus || disabled) return
    setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
    setOpen(true)
  }, [autoFocus, disabled, dropdownPlacement])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!open) return
    const updatePlacement = () => setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
    updatePlacement()
    window.addEventListener('resize', updatePlacement)
    window.addEventListener('scroll', updatePlacement, true)
    return () => {
      window.removeEventListener('resize', updatePlacement)
      window.removeEventListener('scroll', updatePlacement, true)
    }
  }, [open, dropdownPlacement])

  const selectedIds = useMemo(() => {
    if (multi) return Array.isArray(value) ? value : []
    return typeof value === 'number' ? [value] : []
  }, [multi, value])

  const { data: selectedGroup } = useFieldReferenceEmployeeGroup(!multi && selectedIds[0] ? selectedIds[0] : 0)
  const { data: groupsData, isLoading } = useFieldReferenceEmployeeGroups({
    q: debouncedSearch || undefined,
    member_id: memberId ?? undefined,
    page: 1,
    per_page: 20,
  })

  const groups = groupsData?.items ?? []
  const groupMap = useMemo(() => {
    const map = new Map<number, FieldReferenceEmployeeGroupOption>()
    for (const group of groups) map.set(group.id, group)
    if (selectedGroup) map.set(selectedGroup.id, selectedGroup)
    return map
  }, [groups, selectedGroup])

  const selectedLabel = useMemo(() => {
    if (selectedIds.length === 0) return ''
    return selectedIds.map((id) => groupDisplayName(groupMap.get(id), id)).join(', ')
  }, [selectedIds, groupMap])

  const toggleSelection = (groupId: number) => {
    if (multi) {
      const exists = selectedIds.includes(groupId)
      onChange(exists ? selectedIds.filter((id) => id !== groupId) : [...selectedIds, groupId])
      return
    }
    onChange(groupId)
    setOpen(false)
    setSearch('')
  }

  const clearValue = () => {
    onChange(multi ? [] : null)
    setSearch('')
  }

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => {
          if (!open) setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
          setOpen((prev) => !prev)
        }}
        className={cn(
          'flex h-9 w-full items-center gap-2 rounded-md border border-input bg-transparent px-3 text-left text-sm text-foreground outline-none transition-colors',
          'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate', !selectedLabel && 'text-muted-foreground')}>
          {selectedLabel || placeholder}
        </span>
        {!disabled && selectedIds.length > 0 && (
          <span
            onClick={(event) => {
              event.stopPropagation()
              clearValue()
            }}
            className="rounded text-muted-foreground hover:text-foreground"
          >
            <IconX size={14} />
          </span>
        )}
        <IconChevronDown size={14} className="shrink-0 text-muted-foreground" />
      </button>

      {open && !disabled && (
        <div
          className={cn(
            'absolute z-50 w-full rounded-md border border-border bg-background p-2 shadow-lg',
            placement === 'top' ? 'bottom-full mb-1' : 'mt-1',
          )}
        >
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={placeholder}
            className="mb-2 h-8 w-full rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring"
            autoFocus
          />
          <div className="max-h-56 overflow-y-auto">
            {isLoading ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">Loading...</div>
            ) : groups.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">No groups</div>
            ) : (
              groups.map((group) => {
                const selected = selectedIds.includes(group.id)
                return (
                  <button
                    type="button"
                    key={group.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => toggleSelection(group.id)}
                    className={cn('flex w-full flex-col rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent', selected && 'bg-accent')}
                  >
                    <span className="font-medium text-foreground">{group.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {group.description || `${group.member_count} members`}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
