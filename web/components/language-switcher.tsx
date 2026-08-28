'use client'

import { useEffect, useRef, useState } from 'react'
import { IconCheck, IconChevronDown } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { LANGUAGE_OPTIONS } from '@/lib/languages'

/** Pre-login language picker; the chosen locale is persisted to localStorage. */
export function LanguageSwitcher() {
  const { locale, setLocale } = useLocaleStore()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const selected = LANGUAGE_OPTIONS.find((opt) => opt.value === locale)

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <span>{selected?.label ?? locale}</span>
        <IconChevronDown size={16} />
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+4px)] z-20 max-h-80 w-48 overflow-y-auto rounded-lg border border-border bg-white py-1 shadow-lg">
          {LANGUAGE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                setLocale(opt.value)
                setOpen(false)
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-accent"
            >
              <span>{opt.label}</span>
              {opt.value === locale && <IconCheck size={16} className="text-foreground" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
