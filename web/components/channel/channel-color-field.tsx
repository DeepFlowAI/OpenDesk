'use client'

import { useEffect, useRef, useState } from 'react'
import { HexColorPicker } from 'react-colorful'

const HEX_RE = /^#?([0-9a-fA-F]{3,8})$/

function normalizeHex(raw: string): string | null {
  const m = raw.trim().match(HEX_RE)
  if (!m) return null
  let hex = m[1]
  if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2]
  if (hex.length === 6 || hex.length === 8) return `#${hex.toLowerCase()}`
  return null
}

interface ChannelColorFieldProps {
  label: string
  value: string
  onChange: (hex: string) => void
  labelSize?: number
}

export function ChannelColorField({ label, value, onChange, labelSize = 14 }: ChannelColorFieldProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  const display = value || '#f5f5f5'
  const needsBorder = !value || /^#(?:fff(?:fff)?|f5f5f5|FFF(?:FFF)?|F5F5F5)$/i.test(value)

  useEffect(() => {
    if (open) setDraft(value || '')
  }, [open, value])

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handlePickerChange = (hex: string) => {
    setDraft(hex)
    onChange(hex)
  }

  const handleInputChange = (raw: string) => {
    setDraft(raw)
    const hex = normalizeHex(raw)
    if (hex) onChange(hex)
  }

  const handleInputBlur = () => {
    const hex = normalizeHex(draft)
    if (hex) {
      setDraft(hex)
      onChange(hex)
    } else {
      setDraft(value || '')
    }
  }

  const swatchSize = labelSize < 14 ? 18 : 20

  return (
    <div className="relative flex flex-col gap-2" ref={containerRef}>
      <span className="font-medium text-foreground" style={{ fontSize: labelSize }}>{label}</span>

      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-8 w-10 items-center justify-center rounded-lg border border-border"
      >
        <div
          className="rounded"
          style={{
            width: swatchSize,
            height: swatchSize,
            backgroundColor: display,
            border: needsBorder ? '1px solid #e5e5e5' : undefined,
          }}
        />
      </button>

      {open && (
        <div className="absolute top-full left-0 z-50 mt-2 flex flex-col gap-3 rounded-xl border border-border bg-white p-3 shadow-lg">
          <HexColorPicker color={display} onChange={handlePickerChange} style={{ width: 200, height: 160 }} />
          <div className="flex items-center gap-2">
            <div
              className="h-7 w-7 shrink-0 rounded border border-border"
              style={{ backgroundColor: display }}
            />
            <input
              value={draft}
              onChange={(e) => handleInputChange(e.target.value)}
              onBlur={handleInputBlur}
              onKeyDown={(e) => { if (e.key === 'Enter') handleInputBlur() }}
              spellCheck={false}
              className="h-7 w-[130px] rounded-md border border-border bg-white px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="#000000"
            />
          </div>
        </div>
      )}
    </div>
  )
}
