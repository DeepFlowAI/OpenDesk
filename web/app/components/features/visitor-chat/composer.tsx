'use client'

import { useState, useRef, useCallback, type KeyboardEvent, type ChangeEvent } from 'react'
import { IconSend, IconPhoto } from '@tabler/icons-react'

type ComposerProps = {
  placeholder: string
  disabled: boolean
  disabledText: string
  isMobile: boolean
  onSend: (content: string, contentType?: string) => void
  onTyping: () => void
  onImageUpload?: (file: File) => void
}

const MAX_LENGTH = 5000
const MAX_VISIBLE_ROWS = 3

export function Composer({
  placeholder,
  disabled,
  disabledText,
  isMobile,
  onSend,
  onTyping,
}: ComposerProps) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const lineHeight = 22
    const maxHeight = lineHeight * MAX_VISIBLE_ROWS
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
  }, [])

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      const v = e.target.value
      if (v.length > MAX_LENGTH) return
      setText(v)
      adjustHeight()

      if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
      typingTimerRef.current = setTimeout(() => {
        onTyping()
      }, 300)
    },
    [adjustHeight, onTyping]
  )

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, disabled, onSend])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (isMobile) return
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [isMobile, handleSend]
  )

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleImageSelect = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      // TODO: Image upload via OSS, then send as image message
      e.target.value = ''
    },
    []
  )

  return (
    <div className="shrink-0 border-t border-border bg-background px-3 py-2 sm:px-4 sm:py-3">
      <div className="rounded-lg border border-border bg-background shadow-sm">
        <textarea
          ref={textareaRef}
          value={disabled ? '' : text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? disabledText : placeholder}
          disabled={disabled}
          rows={1}
          className="w-full resize-none border-0 bg-transparent px-3 pt-2.5 pb-1 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
          style={{ lineHeight: '22px' }}
        />

        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
              onClick={handleImageSelect}
              disabled={disabled}
            >
              <IconPhoto size={18} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
            onClick={handleSend}
            disabled={disabled || !text.trim()}
          >
            <IconSend size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
