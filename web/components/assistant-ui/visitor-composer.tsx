'use client'

import {
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
  type ChangeEvent,
  type ClipboardEvent as ReactClipboardEvent,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { ComposerPrimitive } from '@assistant-ui/react'
import { useVisitorChatConfig } from './visitor-chat-runtime'
import { EmojiPicker } from './emoji-picker'
import { IconArrowUp, IconLoader2, IconPaperclip, IconPlayerStop, IconStar } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { t } from '@/utils/i18n'

const MAX_ROWS = 3
const LINE_HEIGHT = 22

type PastedImagePreview = {
  file: File
  previewUrl: string
}

const IMAGE_MIME_EXTENSIONS: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
}

function normalizeClipboardImageFile(file: File, fallbackType: string): File {
  if (file.name) return file

  const type = file.type || fallbackType || 'image/png'
  const ext = IMAGE_MIME_EXTENSIONS[type] || 'png'
  return new File([file], `clipboard-image.${ext}`, {
    type,
    lastModified: file.lastModified || Date.now(),
  })
}

function getClipboardImageFile(data: DataTransfer): File | null {
  for (const item of Array.from(data.items)) {
    if (item.kind !== 'file' || !item.type.startsWith('image/')) continue
    const file = item.getAsFile()
    if (file) return normalizeClipboardImageFile(file, item.type)
  }

  for (const file of Array.from(data.files)) {
    if (file.type.startsWith('image/')) return normalizeClipboardImageFile(file, file.type)
  }

  return null
}

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
    offlineMode,
    conversationStatus,
    botRunning,
    handoffRouting,
    visitorMessageCount,
    emojiConfig,
    onTyping,
    onFileSend,
    onAssistSendMessage,
    onRequestHumanHandoff,
  } = useVisitorChatConfig()
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [customButtonPendingIndex, setCustomButtonPendingIndex] = useState<number | null>(null)
  const [pastedImage, setPastedImage] = useState<PastedImagePreview | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const placeholder =
    (offlineMode ? (locale === 'zh' ? '请输入留言...' : 'Leave a message...') : null) ||
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

  useEffect(() => {
    if (!pastedImage) return
    return () => URL.revokeObjectURL(pastedImage.previewUrl)
  }, [pastedImage])

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
        setUploadError(t('ws.chat.attachmentUploadFailed', locale))
      } finally {
        setUploading(false)
      }
    },
    [locale, onFileSend],
  )

  const handlePaste = useCallback(
    (e: ReactClipboardEvent<HTMLTextAreaElement>) => {
      if (disabled || uploading || botMode || botRunning) return

      const imageFile = getClipboardImageFile(e.clipboardData)
      if (!imageFile) return

      e.preventDefault()
      setUploadError(null)
      setPastedImage({
        file: imageFile,
        previewUrl: URL.createObjectURL(imageFile),
      })
    },
    [botMode, botRunning, disabled, uploading],
  )

  const handlePastedImageCancel = useCallback(() => {
    if (uploading) return
    setPastedImage(null)
  }, [uploading])

  const handlePastedImageSend = useCallback(async () => {
    if (!pastedImage || uploading) return

    setUploading(true)
    setUploadError(null)
    try {
      await onFileSend(pastedImage.file)
      setPastedImage(null)
    } catch {
      setUploadError(t('ws.chat.attachmentUploadFailed', locale))
    } finally {
      setUploading(false)
    }
  }, [locale, onFileSend, pastedImage, uploading])

  const showHandoffButton =
    botMode
    && config.open_agent_handoff_enabled
    && visitorMessageCount >= config.open_agent_handoff_after_messages
  const customButtons = useMemo(() => {
    const buttons = botMode
      ? config.open_agent_custom_buttons_enabled ? config.open_agent_custom_buttons : []
      : config.human_custom_buttons_enabled
        && (offlineMode || conversationStatus === 'queued' || conversationStatus === 'active')
        ? config.human_custom_buttons
        : []
    return buttons.filter((button) => button.enabled !== false && button.label.trim())
  }, [
    botMode,
    config.human_custom_buttons,
    config.human_custom_buttons_enabled,
    config.open_agent_custom_buttons,
    config.open_agent_custom_buttons_enabled,
    conversationStatus,
    offlineMode,
  ])
  const showCustomButtonBar = customButtons.length > 0 || showHandoffButton

  const handleCustomButtonClick = useCallback(async (buttonIndex: number) => {
    const button = customButtons[buttonIndex]
    if (!button) return
    if (button.action_type === 'link') {
      const url = button.url?.trim()
      if (!url) return
      window.open(url, '_blank', 'noopener,noreferrer')
      return
    }
    const message = button.message?.trim()
    if (!message || botRunning || handoffRouting) return
    setCustomButtonPendingIndex(buttonIndex)
    try {
      await onAssistSendMessage(message)
    } finally {
      setCustomButtonPendingIndex(null)
    }
  }, [botRunning, customButtons, handoffRouting, onAssistSendMessage])

  return (
    <div className="shrink-0 bg-background px-3 py-2 sm:px-4 sm:py-3">
      {handoffRouting && (
        <div className="mb-2 rounded-lg bg-primary/10 px-3 py-2 text-center text-xs font-medium text-primary">
          {locale === 'zh' ? '正在为您转接人工客服' : 'Connecting you to a human agent…'}
        </div>
      )}
      {showCustomButtonBar && (
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
            {customButtons.map((button, index) => {
              const isSending = customButtonPendingIndex === index
              const sendDisabled =
                disabled
                || (button.action_type === 'send_message' && (botRunning || handoffRouting || customButtonPendingIndex !== null))
              return (
                <button
                  key={`${button.label}-${index}`}
                  type="button"
                  title={button.label}
                  onClick={() => void handleCustomButtonClick(index)}
                  disabled={sendDisabled}
                  className="inline-flex h-8 max-w-[180px] shrink-0 items-center gap-1.5 rounded-full border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isSending && <IconLoader2 size={13} className="shrink-0 animate-spin" />}
                  <span className="truncate">{button.label}</span>
                </button>
              )
            })}
          </div>
          {showHandoffButton && (
            <button
              type="button"
              className="h-8 shrink-0 rounded-full border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
              onClick={() => void onRequestHumanHandoff(null)}
              disabled={disabled || botRunning || handoffRouting}
            >
              {config.open_agent_handoff_label || (locale === 'zh' ? '转人工' : 'Human support')}
            </button>
          )}
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
          onPaste={handlePaste}
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
            {!botMode && (
              <EmojiPicker config={emojiConfig} locale={locale} disabled={disabled || botRunning} />
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
      <Dialog open={pastedImage != null} onOpenChange={(open) => !open && handlePastedImageCancel()}>
        <DialogContent
          className="w-[520px] max-w-[calc(100vw-2rem)] gap-0 overflow-hidden rounded-2xl border border-border bg-background p-0 shadow-lg ring-0"
          showCloseButton={false}
        >
          <DialogTitle className="sr-only">{t('ws.chat.pastedImagePreviewTitle', locale)}</DialogTitle>
          {pastedImage && (
            <>
              <div className="max-h-[70vh] overflow-hidden rounded-t-2xl bg-muted p-4">
                <img
                  src={pastedImage.previewUrl}
                  alt={t('ws.chat.pastedImagePreviewAlt', locale)}
                  className="max-h-[60vh] w-full rounded-xl bg-background object-contain"
                />
              </div>
              {uploadError && (
                <div className="border-t border-border px-4 py-2 text-xs text-destructive">
                  {uploadError}
                </div>
              )}
              <DialogFooter className="rounded-b-2xl border-t border-border px-4 py-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePastedImageCancel}
                  disabled={uploading}
                >
                  {t('ws.common.cancel', locale)}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handlePastedImageSend()}
                  disabled={uploading}
                  className="bg-[var(--opendesk-send-button-bg)] text-primary-foreground hover:opacity-90"
                  style={sendButtonStyle}
                >
                  {uploading && <IconLoader2 size={14} className="animate-spin" />}
                  {t('ws.chat.send', locale)}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
