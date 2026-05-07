'use client'

import { COLOR_RAMPS } from '@/lib/color-ramp-palette'
import { cn } from '@/lib/utils'

function isLightHex(hex: string): boolean {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return true
  const n = parseInt(m[1], 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 215
}

function normalizeHex(c: string | null): string {
  return (c ?? '').trim().toLowerCase()
}

export type RampColorPaletteProps = {
  /** Currently selected color (hex), for ring highlight */
  selectedColor: string | null
  onSelect: (hex: string) => void
  /** When set, shows a clear control to remove color */
  onClear?: () => void
  className?: string
}

/**
 * Multi-row hue ramps with light→dark steps per row (Tailwind-style ramps).
 */
export function RampColorPalette({ selectedColor, onSelect, onClear, className }: RampColorPaletteProps) {
  const sel = normalizeHex(selectedColor)

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {onClear && (
        <button
          type="button"
          onClick={onClear}
          className="flex h-6 w-6 shrink-0 items-center justify-center self-start rounded-full border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Clear color"
        >
          <span className="text-xs leading-none">×</span>
        </button>
      )}

      {/* Padding so borders (not ring/box-shadow) are not clipped by overflow */}
      <div className="flex max-h-[min(280px,45vh)] flex-col gap-1 overflow-y-auto px-1 pb-0.5 pt-1">
        {COLOR_RAMPS.map((row, ri) => (
          <div key={ri} className="flex gap-0.5">
            {row.map((hex, ci) => {
              const active = sel === hex.toLowerCase()
              return (
                <button
                  key={`${ri}-${ci}`}
                  type="button"
                  className={cn(
                    'box-border h-5 w-5 shrink-0 rounded-sm border border-transparent transition-transform hover:z-10 hover:scale-110',
                    isLightHex(hex) && !active && 'border-border/60',
                    active && 'z-10 border-2 border-foreground',
                  )}
                  style={{ backgroundColor: hex }}
                  onClick={() => onSelect(hex)}
                  aria-label={`Select ${hex}`}
                />
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
