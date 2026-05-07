'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronDown, X, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { FdFieldOption } from '@/models/field-definition'

export type OptionComboBoxProps = {
  options: FdFieldOption[]
  /** Single or multi select mode. */
  multi: boolean
  /** string when multi=false, string[] when multi=true, null means empty. */
  value: unknown
  onChange: (v: unknown) => void
  placeholder: string
  disabled?: boolean
  className?: string
}

function normalizeMultiValue(v: unknown): string[] {
  if (v == null) return []
  if (Array.isArray(v)) {
    return v
      .map((x) => (typeof x === 'string' ? x : String(x)))
      .filter((s) => s.length > 0)
  }
  if (typeof v === 'string') {
    return v.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  }
  return []
}

/**
 * Combobox-style option picker with a dropdown panel.
 * Supports both single and multi select, matching TreeSelectEditor visuals.
 */
export function OptionComboBox({
  options,
  multi,
  value,
  onChange,
  placeholder,
  disabled,
  className,
}: OptionComboBoxProps) {
  const [open, setOpen] = useState(false)

  const activeOptions = useMemo(() => options.filter((o) => o.is_active), [options])
  const optionByValue = useMemo(() => {
    const m = new Map<string, FdFieldOption>()
    for (const o of activeOptions) m.set(o.value, o)
    return m
  }, [activeOptions])

  const singleValue = typeof value === 'string' ? value : ''
  const multiValues = useMemo(() => (multi ? normalizeMultiValue(value) : []), [multi, value])

  const isPlaceholder = multi ? multiValues.length === 0 : !singleValue

  const close = useCallback(() => setOpen(false), [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, close])

  const toggle = useCallback(
    (optValue: string) => {
      if (multi) {
        const next = multiValues.includes(optValue)
          ? multiValues.filter((x) => x !== optValue)
          : [...multiValues, optValue]
        onChange(next.length > 0 ? next : null)
      } else {
        onChange(optValue)
        close()
      }
    },
    [multi, multiValues, onChange, close],
  )

  const removeMultiValue = useCallback(
    (optValue: string) => {
      const next = multiValues.filter((x) => x !== optValue)
      onChange(next.length > 0 ? next : null)
    },
    [multiValues, onChange],
  )

  return (
    <div className={cn('relative w-full', className)}>
      <div
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((o) => !o)
          }
        }}
        className={cn(
          'flex min-h-9 w-full cursor-pointer items-center justify-between gap-1.5 rounded-md border border-input bg-transparent py-1 pr-2 pl-2.5 text-left text-sm transition-colors outline-none select-none',
          'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
          'dark:bg-input/30',
          disabled && 'pointer-events-none cursor-not-allowed opacity-50',
          multi && multiValues.length > 0 && 'h-auto',
          isPlaceholder && 'text-muted-foreground',
        )}
      >
        {multi && multiValues.length > 0 ? (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1 py-0.5">
            {multiValues.map((v) => {
              const opt = optionByValue.get(v)
              return (
                <span
                  key={v}
                  className="inline-flex min-h-5 max-w-full items-center gap-1 rounded border border-border/80 bg-muted/70 py-0.5 pr-0.5 pl-1.5 text-xs text-foreground"
                >
                  {opt?.color && (
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: opt.color }}
                    />
                  )}
                  <span className="min-w-0 flex-1 truncate" title={opt?.label ?? v}>
                    {opt?.label ?? v}
                  </span>
                  <button
                    type="button"
                    className="inline-flex shrink-0 cursor-pointer items-center justify-center rounded p-0.5 text-muted-foreground hover:bg-background/80 hover:text-foreground"
                    onClick={(e) => {
                      e.stopPropagation()
                      e.preventDefault()
                      if (!disabled) removeMultiValue(v)
                    }}
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </span>
              )
            })}
          </div>
        ) : !multi && singleValue ? (
          <span className="inline-flex min-w-0 flex-1 items-center gap-1.5 truncate leading-5">
            {optionByValue.get(singleValue)?.color && (
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: optionByValue.get(singleValue)!.color! }}
              />
            )}
            <span className="truncate">
              {optionByValue.get(singleValue)?.label ?? singleValue}
            </span>
          </span>
        ) : (
          <span className="min-w-0 flex-1 truncate leading-5">{placeholder}</span>
        )}
        <ChevronDown
          className={cn(
            'size-4 shrink-0 self-center text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </div>

      {open && (
        <>
          <div className="fixed inset-0 z-40" aria-hidden onClick={close} />
          <div
            className={cn(
              'absolute top-full right-0 left-0 z-50 mt-1 max-h-[min(320px,50vh)] overflow-auto rounded-lg border border-border bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10',
            )}
          >
            {activeOptions.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-muted-foreground">
                {placeholder}
              </div>
            ) : (
              <ul role="listbox" className="py-1">
                {activeOptions.map((opt) => {
                  const selected = multi
                    ? multiValues.includes(opt.value)
                    : opt.value === singleValue
                  return (
                    <li key={opt.id ?? opt.value}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={selected}
                        onClick={() => toggle(opt.value)}
                        className={cn(
                          'flex w-full cursor-pointer items-center gap-2 px-2.5 py-1.5 text-left text-sm transition-colors',
                          'hover:bg-accent',
                          selected && !multi && 'bg-[#e6f7ff] dark:bg-sky-950/45',
                        )}
                      >
                        {multi && (
                          <span
                            className={cn(
                              'flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors',
                              selected
                                ? 'border-primary bg-primary text-primary-foreground'
                                : 'border-input',
                            )}
                            aria-hidden
                          >
                            {selected && <Check className="size-3" />}
                          </span>
                        )}
                        {opt.color && (
                          <span
                            className="h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{ backgroundColor: opt.color }}
                          />
                        )}
                        <span className="min-w-0 flex-1 truncate">{opt.label}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
