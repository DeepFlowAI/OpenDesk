'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { IconChevronDown, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'

/** Normalized option for select UIs; compatible with FdFieldOption and config-only options. */
export type FieldSelectOption = {
  value: string
  label: string
  color: string | null
  is_active: boolean
  sort_order?: number
}

export function normalizePillOptions(
  options: FieldSelectOption[] | undefined,
): FieldSelectOption[] {
  if (!options?.length) return []
  return [...options]
    .filter((o) => o.is_active !== false)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
    .map((o) => ({
      value: o.value,
      label: o.label,
      color: o.color ?? null,
      is_active: o.is_active !== false,
      sort_order: o.sort_order,
    }))
}

/** type_config.options (no id) — for system fields with inline options; supports optional `color`. */
export function optionsFromTypeConfigList(
  options: { label: string; value: string; color?: string | null }[] | undefined,
): FieldSelectOption[] {
  if (!options?.length) return []
  return options.map((o, i) => ({
    value: o.value,
    label: o.label,
    color: o.color ?? null,
    is_active: true,
    sort_order: i,
  }))
}

/** Use DB options when present, otherwise `type_config.options` (system field definitions). */
export function coalescePillOptions(
  options:
    | Array<{
        value: string
        label: string
        color?: string | null
        is_active?: boolean
        sort_order?: number
      }>
    | undefined,
  typeConfig: Record<string, unknown>,
): FieldSelectOption[] {
  if (options?.length) {
    return normalizePillOptions(
      options.map((o) => ({
        value: o.value,
        label: o.label,
        color: o.color ?? null,
        is_active: o.is_active !== false,
        sort_order: o.sort_order,
      })),
    )
  }
  return optionsFromTypeConfigList(
    (typeConfig.options as { label: string; value: string }[] | undefined) ?? undefined,
  )
}

/**
 * Renders a single option as a soft pill. When `color` is null, uses neutral border/muted background.
 */
export function FieldOptionPill({
  label,
  color,
  className,
  dimmed = false,
}: {
  label: string
  color: string | null
  className?: string
  /** Lower emphasis (e.g. unselected in multi) */
  dimmed?: boolean
}) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full min-w-0 items-center truncate rounded-full px-2.5 py-0.5 text-sm font-normal',
        // Softer than full foreground — colored pills look harsh with pure black on saturated fills
        color ? 'text-foreground/75' : 'text-foreground/80 border border-border bg-muted/60',
        dimmed && 'opacity-50',
        className,
      )}
      style={color ? { backgroundColor: color } : undefined}
    >
      {label}
    </span>
  )
}

const comboboxInputClass =
  'flex w-full min-h-9 items-center justify-between gap-1 rounded-md border border-border bg-transparent px-2.5 text-sm outline-none transition-[box-shadow] focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

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

type PillSelectComboboxProps = {
  value: string | null | undefined
  onChange: (v: string | null) => void
  options: FieldSelectOption[]
  placeholder: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  /** Fires after a value is chosen (e.g. end inline edit on ticket row) */
  onAfterChange?: (v: string | null) => void
  /** Input border class when focused (inline edit on ticket) */
  inputClassName?: string
}

/**
 * Custom single select: pill in trigger, pills in list, clear control when value is set.
 */
export function PillSelectCombobox({
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
  className,
  autoFocus = false,
  onAfterChange,
  inputClassName,
}: PillSelectComboboxProps) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom')
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const strVal = value != null && value !== '' ? String(value) : ''
  const selected = useMemo(
    () => (strVal ? options.find((o) => o.value === strVal) : undefined),
    [options, strVal],
  )

  useEffect(() => {
    if (!autoFocus || disabled) return
    triggerRef.current?.focus()
    setPlacement(getDropdownPlacement(rootRef.current))
    setOpen(true)
  }, [autoFocus, disabled])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  useEffect(() => {
    if (!open) return
    const updatePlacement = () => setPlacement(getDropdownPlacement(rootRef.current))
    updatePlacement()
    window.addEventListener('resize', updatePlacement)
    window.addEventListener('scroll', updatePlacement, true)
    return () => {
      window.removeEventListener('resize', updatePlacement)
      window.removeEventListener('scroll', updatePlacement, true)
    }
  }, [open])

  const pick = useCallback(
    (v: string | null) => {
      onChange(v)
      onAfterChange?.(v)
      setOpen(false)
    },
    [onChange, onAfterChange],
  )

  return (
    <div ref={rootRef} className={cn('relative w-full', className)}>
      <div
        className={cn(
          comboboxInputClass,
          open && 'ring-1 ring-ring',
          inputClassName,
        )}
      >
        <button
          ref={triggerRef}
          type="button"
          disabled={disabled}
          onClick={() => {
            if (disabled) return
            if (!open) setPlacement(getDropdownPlacement(rootRef.current))
            setOpen((o) => !o)
          }}
          className="flex min-w-0 flex-1 items-center gap-1 text-left"
        >
          {selected ? (
            <FieldOptionPill label={selected.label} color={selected.color} />
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
        </button>
        <div className="flex shrink-0 items-center gap-0.5">
          {strVal && !disabled && (
            <button
              type="button"
              className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={(e) => {
                e.stopPropagation()
                pick(null)
              }}
              aria-label="Clear"
            >
              <IconX size={14} stroke={1.5} />
            </button>
          )}
          <span className="pointer-events-none text-muted-foreground">
            <IconChevronDown size={16} />
          </span>
        </div>
      </div>

      {open && !disabled && (
        <ul
          role="listbox"
          className={cn(
            'absolute left-0 right-0 z-50 max-h-60 overflow-y-auto rounded-lg border border-border bg-popover p-1.5 text-popover-foreground shadow-md ring-1 ring-foreground/10',
            placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1',
          )}
        >
          <li
            className="cursor-default rounded-md px-1 py-0.5 text-sm text-muted-foreground hover:bg-accent/50"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => pick(null)}
            role="option"
          >
            {placeholder}
          </li>
          {options.map((opt) => {
            const active = strVal === opt.value
            return (
              <li
                key={opt.value}
                role="option"
                aria-selected={active}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(opt.value)}
                className={cn(
                  'cursor-default rounded-md px-1.5 py-1 transition-colors',
                  active ? 'bg-primary/10' : 'hover:bg-muted/80',
                )}
              >
                <FieldOptionPill label={opt.label} color={opt.color} />
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

type PillMultiSelectFieldProps = {
  value: string[]
  onChange: (v: string[] | null) => void
  options: FieldSelectOption[]
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
}

/**
 * Clickable option pills; supports optional background color from backend.
 */
export function PillMultiSelectField({
  value,
  onChange,
  options,
  placeholder: _ph,
  disabled = false,
  className,
  autoFocus = false,
}: PillMultiSelectFieldProps) {
  const selected = value ?? []
  const firstOptionRef = useRef<HTMLInputElement>(null)
  const activeOptions = useMemo(
    () => options.filter((o) => o.is_active !== false),
    [options],
  )

  useEffect(() => {
    if (!autoFocus || disabled) return
    firstOptionRef.current?.focus()
  }, [autoFocus, disabled])

  const toggle = useCallback(
    (optValue: string) => {
      const next = selected.includes(optValue)
        ? selected.filter((v) => v !== optValue)
        : [...selected, optValue]
      onChange(next.length > 0 ? next : null)
    },
    [selected, onChange],
  )

  if (activeOptions.length === 0) {
    return (
      <span className={cn('text-sm text-muted-foreground', className)}>{_ph ?? '—'}</span>
    )
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {activeOptions.map((opt) => {
        const checked = selected.includes(opt.value)
        const withColor = Boolean(opt.color)
        return (
          <label
            key={opt.value}
            className={cn(
              'inline-flex cursor-pointer items-center text-sm transition-colors',
              withColor
                ? disabled && 'cursor-not-allowed opacity-50'
                : [
                    'gap-1.5 rounded-md border px-3 py-1.5',
                    checked
                      ? 'border-primary bg-primary/5 text-foreground/80'
                      : 'border-border text-muted-foreground',
                    disabled && 'cursor-not-allowed opacity-50',
                  ],
            )}
          >
            <input
              ref={autoFocus && opt === activeOptions[0] ? firstOptionRef : undefined}
              type="checkbox"
              checked={checked}
              onChange={() => toggle(opt.value)}
              disabled={disabled}
              className="sr-only"
            />
            {withColor ? (
              <FieldOptionPill label={opt.label} color={opt.color} dimmed={!checked} />
            ) : (
              opt.label
            )}
          </label>
        )
      })}
    </div>
  )
}
