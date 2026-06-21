'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useComposerRuntime } from '@assistant-ui/react'
import { IconMoodSmile } from '@tabler/icons-react'
import type { Locale } from '@/context/locale-store'
import type { EmojiItem, EmojiTargetConfig } from '@/models/emoji-setting'
import { getEmojiAlias, getEmojiName } from '@/lib/emoji-catalog'

type EmojiPickerProps = {
  config: EmojiTargetConfig | null | undefined
  locale: Locale
  disabled?: boolean
  onEmojiPick?: (emoji: string) => void
}

function findComposerTextarea(button: HTMLButtonElement | null): HTMLTextAreaElement | null {
  const form = button?.closest('form')
  return form?.querySelector<HTMLTextAreaElement>('textarea[name="input"]') ?? form?.querySelector('textarea') ?? null
}

export function EmojiPicker({ config, locale, disabled = false, onEmojiPick }: EmojiPickerProps) {
  const composer = useComposerRuntime()
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const emojis = config?.enabled ? config.emojis : []
  const label = locale === 'zh' ? '插入表情' : 'Insert emoji'
  const panelTitle = locale === 'zh' ? '选择表情' : 'Choose emoji'

  const grouped = useMemo(() => emojis.slice(0, 48), [emojis])

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

  if (!config?.enabled || grouped.length === 0) return null

  const handlePick = (item: EmojiItem) => {
    if (onEmojiPick) {
      onEmojiPick(item.emoji)
      setOpen(false)
      return
    }

    const text = composer.getState().text
    const textarea = findComposerTextarea(buttonRef.current)
    const hasSelection = textarea && document.activeElement === textarea
    const start = hasSelection ? textarea.selectionStart : text.length
    const end = hasSelection ? textarea.selectionEnd : text.length
    const nextText = `${text.slice(0, start)}${item.emoji}${text.slice(end)}`
    const nextCursor = start + item.emoji.length

    composer.setText(nextText)
    setOpen(false)
    window.requestAnimationFrame(() => {
      textarea?.focus({ preventScroll: true })
      try {
        textarea?.setSelectionRange(nextCursor, nextCursor)
      } catch {
        // Ignore host selection limitations.
      }
    })
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
        aria-label={label}
        title={label}
        aria-expanded={open}
      >
        <IconMoodSmile size={18} stroke={1.5} />
      </button>
      {open && (
        <div className="absolute bottom-10 left-0 z-40 w-[284px] rounded-lg border border-border bg-background p-3 shadow-lg">
          <div className="mb-2 text-xs font-medium text-muted-foreground">{panelTitle}</div>
          <div className="grid max-h-[220px] grid-cols-8 gap-1 overflow-y-auto pr-1">
            {grouped.map((item) => (
              <button
                key={item.emoji}
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-md text-lg transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => handlePick(item)}
                aria-label={`${label}: ${getEmojiName(item, locale)}`}
                title={getEmojiAlias(item, locale)}
              >
                {item.emoji}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
