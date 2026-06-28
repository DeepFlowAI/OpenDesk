'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconChevronDown, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import {
  useFieldReferenceEmployee,
  useFieldReferenceEmployees,
  type FieldReferenceEmployeeOption,
} from '@/service/use-field-reference-options'

type EmployeeSelectProps = {
  value: number | number[] | null | undefined
  onChange: (value: number | number[] | null) => void
  multi?: boolean
  disabled?: boolean
  placeholder?: string
  groupId?: number | null
  className?: string
  dropdownPlacement?: 'top' | 'bottom'
  autoFocus?: boolean
}

function employeeDisplayName(employee: FieldReferenceEmployeeOption | undefined, fallbackId?: number): string {
  if (!employee) return fallbackId ? `Employee #${fallbackId}` : ''
  const primary = employee.nickname || employee.name || employee.username
  const secondary = employee.job_number || employee.email || employee.phone
  return secondary ? `${primary} · ${secondary}` : primary
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

export function EmployeeSelect({
  value,
  onChange,
  multi = false,
  disabled = false,
  placeholder = 'Search employees...',
  groupId,
  className,
  dropdownPlacement,
  autoFocus = false,
}: EmployeeSelectProps) {
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

  const { data: selectedEmployee } = useFieldReferenceEmployee(!multi && selectedIds[0] ? selectedIds[0] : 0)
  const { data: employeesData, isLoading } = useFieldReferenceEmployees({
    q: debouncedSearch || undefined,
    group_id: groupId ?? undefined,
    page: 1,
    per_page: 20,
  })

  const employees = employeesData?.items ?? []
  const employeeMap = useMemo(() => {
    const map = new Map<number, FieldReferenceEmployeeOption>()
    for (const employee of employees) map.set(employee.id, employee)
    if (selectedEmployee) map.set(selectedEmployee.id, selectedEmployee)
    return map
  }, [employees, selectedEmployee])

  const selectedLabel = useMemo(() => {
    if (selectedIds.length === 0) return ''
    return selectedIds.map((id) => employeeDisplayName(employeeMap.get(id), id)).join(', ')
  }, [selectedIds, employeeMap])

  const toggleSelection = (employeeId: number) => {
    if (multi) {
      const exists = selectedIds.includes(employeeId)
      onChange(exists ? selectedIds.filter((id) => id !== employeeId) : [...selectedIds, employeeId])
      return
    }
    onChange(employeeId)
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
            ) : employees.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">No employees</div>
            ) : (
              employees.map((employee) => {
                const selected = selectedIds.includes(employee.id)
                return (
                  <button
                    type="button"
                    key={employee.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => toggleSelection(employee.id)}
                    className={cn('flex w-full flex-col rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent', selected && 'bg-accent')}
                  >
                    <span className="font-medium text-foreground">
                      {employee.nickname || employee.name || employee.username}
                    </span>
                    {(employee.job_number || employee.email || employee.phone) && (
                      <span className="text-xs text-muted-foreground">
                        {employee.job_number || employee.email || employee.phone}
                      </span>
                    )}
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
