'use client'

import {
  useState,
  useRef,
  useCallback,
  type ChangeEvent,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { ComposerPrimitive } from '@assistant-ui/react'
import { useVisitorChatConfig } from './visitor-chat-runtime'
import { IconArrowUp, IconLoader2, IconPaperclip, IconPlayerStop, IconStar } from '@tabler/icons-react'

const MAX_ROWS = 3
const LINE_HEIGHT = 22

function focusComposerTextarea(e: ReactPointerEvent<HTMLElement>) {
  // Prevent default so the click target does not participate in focus routing
  // (otherwise the textarea often never receives caret on this filler strip).
  e.preventDefault()
  const form = e.currentTarget.closest('form')
  const ta =
    form?.querySelector<HTMLTextAreaElement>('textarea[name="input"]') ??
    form?.querySelector('textarea')
  if (!ta || ta.disabled) return
  window.requestAnimationFrame(() => {
    ta.focus({ preventScroll: true })
    const len = ta.value.length
    try {
      ta.setSelectionRange(len, len)
    } catch {
      // Some hosts leave selection APIs unavailable; focus alone is enough
    }
  })
}

type VisitorComposerProps = {
  disabled: boolean
  isMobile: boolean
  isEmbed?: boolean
  showSatisfactionButton?: boolean
  satisfactionLoading?: boolean
  onSatisfactionClick?: () => void
}

export function VisitorComposer({
  disabled,
  isMobile,
  isEmbed = false,
  showSatisfactionButton = false,
  satisfactionLoading = false,
  onSatisfactionClick,
}: VisitorComposerProps) {
  const {
    locale,
    config,
    botMode,
    botRunning,
    handoffRouting,
    visitorMessageCount,
    onTyping,
    onFileSend,
    onRequestHumanHandoff,
  } = useVisitorChatConfig()
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const placeholder =
    (botMode ? config.open_agent_input_placeholder : config.input_placeholder) ||
    (locale === 'zh' ? '输入消息...' : 'Type a message...')
  const disabledText =
    locale === 'zh' ? '会话已结束' : 'Conversation ended'
  const sendButtonStyle = {
    '--opendesk-send-button-bg': config.send_button_bg_color || 'var(--color-primary)',
  } as CSSProperties

  const handleTypingDebounce = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const content = e.currentTarget.value
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(() => onTyping(content), 300)
  }, [onTyping])

  const handleImageSelect = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      e.target.value = ''
      if (!file) return

      setUploading(true)
      setUploadError(null)
      try {
        await onFileSend(file)
      } catch {
        setUploadError(locale === 'zh' ? '上传失败，请重试' : 'Upload failed. Please try again.')
      } finally {
        setUploading(false)
      }
    },
    [locale, onFileSend],
  )

  const showHandoffButton =
    botMode
    && config.open_agent_handoff_enabled
    && visitorMessageCount >= config.open_agent_handoff_after_messages

  return (
    <div className="shrink-0 bg-background px-3 py-2 sm:px-4 sm:py-3">
      {handoffRouting && (
        <div className="mb-2 rounded-lg bg-primary/10 px-3 py-2 text-center text-xs font-medium text-primary">
          {locale === 'zh' ? '正在为您转接人工客服' : 'Connecting you to a human agent…'}
        </div>
      )}
      {showHandoffButton && (
        <div className="mb-2 flex justify-start">
          <button
            type="button"
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void onRequestHumanHandoff(null)}
            disabled={disabled || botRunning || handoffRouting}
          >
            {config.open_agent_handoff_label || (locale === 'zh' ? '转人工' : 'Human support')}
          </button>
        </div>
      )}
      <ComposerPrimitive.Root className="rounded-[14px] border border-border bg-background sm:rounded-2xl">
        {/* Text input */}
        <ComposerPrimitive.Input
          placeholder={disabled ? disabledText : placeholder}
          disabled={disabled}
          submitMode={isMobile && !isEmbed ? 'none' : 'enter'}
          rows={1}
          maxRows={MAX_ROWS}
          onChange={handleTypingDebounce}
          className="w-full resize-none border-0 bg-transparent px-3 pt-2.5 pb-1 text-sm text-foreground outline-none placeholder:text-[#9CA3AF] disabled:cursor-not-allowed disabled:opacity-50 sm:px-4 sm:pt-3"
          style={{ lineHeight: `${LINE_HEIGHT}px` }}
        />

        {/* Action bar */}
        <div className="flex items-center justify-between px-2 pb-2 sm:px-3 sm:pb-2.5">
          {/* Left: attachment button */}
          <div className="flex items-center gap-1">
            {!botMode && (
              <button
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                onClick={handleImageSelect}
                disabled={disabled || uploading}
              >
                {uploading ? <IconLoader2 size={18} className="animate-spin" /> : <IconPaperclip size={18} />}
              </button>
            )}
            {!botMode && showSatisfactionButton && (
              <button
                type="button"
                className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
                onClick={onSatisfactionClick}
                disabled={disabled || satisfactionLoading}
                aria-label={locale === 'zh' ? '满意度评价' : 'Rate this conversation'}
                title={locale === 'zh' ? '满意度评价' : 'Rate this conversation'}
              >
                {satisfactionLoading ? (
                  <IconLoader2 size={18} className="animate-spin" />
                ) : (
                  <IconStar size={18} stroke={1.5} />
                )}
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.md,.zip,.rar,.7z"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          <div
            role="presentation"
            className="min-h-8 flex-1 cursor-text self-stretch"
            onPointerDown={(e) => {
              if (e.button !== 0) return
              focusComposerTextarea(e)
            }}
          />

          {botRunning ? (
            <ComposerPrimitive.Cancel
              className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full bg-[var(--opendesk-send-button-bg)] text-primary-foreground transition-opacity hover:opacity-90 sm:h-9 sm:w-9"
              style={sendButtonStyle}
            >
              <IconPlayerStop size={isMobile ? 16 : 18} />
            </ComposerPrimitive.Cancel>
          ) : (
            <ComposerPrimitive.Send
              disabled={disabled}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#F4F4F5] text-[#9CA3AF] transition-colors enabled:cursor-pointer enabled:bg-[var(--opendesk-send-button-bg)] enabled:text-primary-foreground enabled:hover:opacity-90 disabled:cursor-not-allowed sm:h-9 sm:w-9"
              style={sendButtonStyle}
            >
              <IconArrowUp size={isMobile ? 16 : 18} />
            </ComposerPrimitive.Send>
          )}
        </div>
        {uploadError && (
          <div className="px-3 pb-2 text-xs text-destructive sm:px-4">
            {uploadError}
          </div>
        )}
      </ComposerPrimitive.Root>
    </div>
  )
}
