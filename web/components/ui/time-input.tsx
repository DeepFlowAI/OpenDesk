'use client'

import * as React from 'react'
import { Input as InputPrimitive } from '@base-ui/react/input'

import { cn } from '@/lib/utils'

const inputClass =
  'h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40'

type PickableType = 'date' | 'time' | 'datetime-local'

type PickableInputProps = Omit<React.ComponentProps<'input'>, 'type'> & {
  type: PickableType
}

/**
 * Opens the native browser picker on full-field click (showPicker), not only the calendar/clock icon.
 */
function PickableInput({ type, className, disabled, onClick, ...props }: PickableInputProps) {
  const ref = React.useRef<HTMLInputElement>(null)

  const handleClick = (e: React.MouseEvent<HTMLInputElement>) => {
    onClick?.(e)
    if (disabled || e.defaultPrevented) return
    const el = ref.current
    if (!el) return
    if (typeof el.showPicker === 'function') {
      try {
        void el.showPicker()
      } catch {
        el.focus()
      }
    }
  }

  return (
    <InputPrimitive
      ref={ref}
      type={type}
      data-slot="input"
      disabled={disabled}
      className={cn(inputClass, className)}
      onClick={handleClick}
      {...props}
    />
  )
}

export type TimeInputProps = Omit<React.ComponentProps<'input'>, 'type'>
export type DateInputProps = Omit<React.ComponentProps<'input'>, 'type'>
export type DateTimeInputProps = Omit<React.ComponentProps<'input'>, 'type'>

/**
 * datetime-local only accepts "yyyy-MM-ddThh:mm" in local time (no timezone suffix).
 * ISO strings like "2026-04-07T00:12:00+00:00" are rejected and render as empty.
 */
function toDatetimeLocalInputValue(raw: string): string {
  const s = raw.trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s)) return s
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function coerceInputValueToString(value: DateTimeInputProps['value']): string {
  if (value == null || value === '') return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return String(value[0] ?? '')
  return String(value)
}

function TimeInput({ ...props }: TimeInputProps) {
  return <PickableInput type="time" {...props} />
}

function DateInput({ ...props }: DateInputProps) {
  return <PickableInput type="date" {...props} />
}

function DateTimeInput({ value, ...props }: DateTimeInputProps) {
  const normalized =
    value == null || value === '' ? '' : toDatetimeLocalInputValue(coerceInputValueToString(value))

  return <PickableInput type="datetime-local" value={normalized} {...props} />
}

export { TimeInput, DateInput, DateTimeInput }
