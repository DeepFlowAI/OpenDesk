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
import { ComposerPrimitive, useComposerRuntime } from '@assistant-ui/react'
import { useVisitorChatConfig } from './visitor-chat-runtime'
import { EmojiPicker } from './emoji-picker'
import { IconArrowUp, IconLoader2, IconPaperclip, IconPlayerStop, IconStar } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { t } from '@/utils/i18n'
import { MessageQuotePreview } from '@/app/components/features/chat/message-quote'
import type { Message } from '@/models/conversation'
import { quoteFromMessage } from '@/lib/message-quote'

const MAX_ROWS = 3
const LINE_HEIGHT = 22

type PastedAttachmentPreview = {
  file: File
  previewUrl: string | null
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

function normalizeClipboardFile(file: File, fallbackType: string): File {
  if (file.name) return file
  if ((file.type || fallbackType).startsWith('image/')) return normalizeClipboardImageFile(file, fallbackType)

  return new File([file], 'clipboard-attachment', {
    type: file.type || fallbackType || 'application/octet-stream',
    lastModified: file.lastModified || Date.now(),
  })
}

function getClipboardAttachmentFile(data: DataTransfer): File | null {
  for (const item of Array.from(data.items)) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (file) return normalizeClipboardFile(file, item.type)
  }

  for (const file of Array.from(data.files)) {
    return normalizeClipboardFile(file, file.type)
  }

  return null
}

function getPastedAttachmentPreviewUrl(file: File): string | null {
  return file.type.startsWith('image/') ? URL.createObjectURL(file) : null
}

function formatAttachmentSize(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB']
  let value = size
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }

  const digits = unitIndex === 0 || value >= 10 ? 0 : 1
  return `${value.toFixed(digits)} ${units[unitIndex]}`
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
  insertRequest?: VisitorComposerInsertRequest | null
  showSatisfactionButton?: boolean
  satisfactionLoading?: boolean
  onSatisfactionClick?: () => void
}

export type VisitorComposerInsertRequest = {
  id: number
  text: string
  contentType?: 'text' | 'rich_text'
  quotedMessage?: Message | null
}

export function VisitorComposer({
  disabled,
  isMobile,
  isEmbed = false,
  insertRequest,
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
    quotedMessage,
    onQuoteMessage,
    onClearQuote,
    visitorSessionToken,
  } = useVisitorChatConfig()
  const composer = useComposerRuntime()
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [customButtonPendingIndex, setCustomButtonPendingIndex] = useState<number | null>(null)
  const [pastedAttachment, setPastedAttachment] = useState<PastedAttachmentPreview | null>(null)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInsertIdRef = useRef<number | null>(null)

  // Enter-to-send should only fall back to newline on real touch devices
  // (phone/tablet soft keyboards), not on narrow desktop windows. Viewport
  // width alone misclassifies a narrow embedded widget as "mobile".
  const [isTouchDevice, setIsTouchDevice] = useState(false)
  useEffect(() => {
    setIsTouchDevice(window.matchMedia?.('(pointer: coarse)').matches ?? false)
  }, [])

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

  // When the input transitions to empty (message sent or draft cleared), cancel
  // any pending typing emit and immediately tell the agent to stop the "visitor
  // typing" preview — otherwise a debounced typing event can land after the
  // message and leave a stale preview lingering next to the delivered message.
  const prevComposerTextRef = useRef('')
  useEffect(() => {
    return composer.subscribe(() => {
      const text = composer.getState().text
      const wasNonEmpty = prevComposerTextRef.current.length > 0
      prevComposerTextRef.current = text
      if (wasNonEmpty && text.length === 0) {
        if (typingTimerRef.current) {
          clearTimeout(typingTimerRef.current)
          typingTimerRef.current = null
        }
        onTyping('')
      }
    })
  }, [composer, onTyping])

  useEffect(() => {
    const previewUrl = pastedAttachment?.previewUrl
    if (!previewUrl) return
    return () => URL.revokeObjectURL(previewUrl)
  }, [pastedAttachment])

  // Move focus into the composer right after a message is quoted, so the
  // visitor can start typing immediately instead of clicking the input first.
  const prevQuotedIdRef = useRef<number | null>(null)
  useEffect(() => {
    const quotedId = quotedMessage?.id ?? null
    const becameQuoted = quotedId !== null && prevQuotedIdRef.current !== quotedId
    prevQuotedIdRef.current = quotedId
    if (!becameQuoted || disabled || offlineMode) return
    window.requestAnimationFrame(() => {
      const textarea =
        rootRef.current?.querySelector<HTMLTextAreaElement>('textarea[name="input"]') ??
        rootRef.current?.querySelector<HTMLTextAreaElement>('textarea')
      if (!textarea || textarea.disabled) return
      textarea.focus({ preventScroll: true })
      const len = textarea.value.length
      try {
        textarea.setSelectionRange(len, len)
      } catch {
        // Some hosts leave selection APIs unavailable; focus alone is enough.
      }
    })
  }, [disabled, offlineMode, quotedMessage])

  useEffect(() => {
    if (!insertRequest || disabled || lastInsertIdRef.current === insertRequest.id) return

    lastInsertIdRef.current = insertRequest.id
    const restoreQuote = () => {
      if (!Object.prototype.hasOwnProperty.call(insertRequest, 'quotedMessage')) return
      if (insertRequest.quotedMessage) onQuoteMessage(insertRequest.quotedMessage)
      else onClearQuote()
    }
    const currentText = composer.getState().text
    if (currentText.trim()) {
      const confirmed = window.confirm(t('ws.chat.recall.replaceDraftConfirm', locale))
      if (!confirmed) return
      composer.setText('')
    }

    composer.setText(insertRequest.text)
    restoreQuote()
    const textarea =
      rootRef.current?.querySelector<HTMLTextAreaElement>('textarea[name="input"]') ??
      rootRef.current?.querySelector<HTMLTextAreaElement>('textarea')
    window.requestAnimationFrame(() => {
      textarea?.focus({ preventScroll: true })
      try {
        textarea?.setSelectionRange(insertRequest.text.length, insertRequest.text.length)
      } catch {
        // Ignore host selection limitations.
      }
    })
  }, [composer, disabled, insertRequest, locale, onClearQuote, onQuoteMessage])

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

      const attachmentFile = getClipboardAttachmentFile(e.clipboardData)
      if (!attachmentFile) return

      e.preventDefault()
      setUploadError(null)
      setPastedAttachment({
        file: attachmentFile,
        previewUrl: getPastedAttachmentPreviewUrl(attachmentFile),
      })
    },
    [botMode, botRunning, disabled, uploading],
  )

  const handlePastedAttachmentCancel = useCallback(() => {
    if (uploading) return
    setPastedAttachment(null)
  }, [uploading])

  const handlePastedAttachmentSend = useCallback(async () => {
    if (!pastedAttachment || uploading) return

    setUploading(true)
    setUploadError(null)
    try {
      await onFileSend(pastedAttachment.file)
      setPastedAttachment(null)
    } catch {
      setUploadError(t('ws.chat.attachmentUploadFailed', locale))
    } finally {
      setUploading(false)
    }
  }, [locale, onFileSend, pastedAttachment, uploading])

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
  const quotePreview = quotedMessage && !offlineMode
    ? quoteFromMessage(quotedMessage, locale)
    : null

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
    <div ref={rootRef} className="shrink-0 bg-background px-3 py-2 sm:px-4 sm:py-3">
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
        {quotePreview && quotedMessage && (
          <MessageQuotePreview
            quote={quotePreview}
            locale={locale}
            original={quotedMessage}
            onRemove={onClearQuote}
            audience="visitor"
            attachmentContext={{
              conversationId: quotedMessage.conversation_id,
              conversationPublicId: quotedMessage.conversation_public_id,
              visitorSessionToken,
            }}
            className="mx-2 mt-2 sm:mx-3 sm:mt-3 [&>:first-child]:bg-primary/50"
          />
        )}
        {/* Text input */}
        <ComposerPrimitive.Input
          placeholder={disabled ? disabledText : placeholder}
          disabled={disabled}
          submitMode={isTouchDevice && !isEmbed ? 'none' : 'enter'}
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
      <Dialog open={pastedAttachment != null} onOpenChange={(open) => !open && handlePastedAttachmentCancel()}>
        <DialogContent
          className="w-[520px] max-w-[calc(100vw-2rem)] gap-0 overflow-hidden rounded-2xl border border-border bg-background p-0 shadow-lg ring-0"
          showCloseButton={false}
        >
          <DialogTitle className="sr-only">
            {t(pastedAttachment?.previewUrl ? 'ws.chat.pastedImagePreviewTitle' : 'ws.chat.pastedAttachmentPreviewTitle', locale)}
          </DialogTitle>
          {pastedAttachment && (
            <>
              {pastedAttachment.previewUrl ? (
                <div className="max-h-[70vh] overflow-hidden rounded-t-2xl bg-muted p-4">
                  <img
                    src={pastedAttachment.previewUrl}
                    alt={t('ws.chat.pastedImagePreviewAlt', locale)}
                    className="max-h-[60vh] w-full rounded-xl bg-background object-contain"
                  />
                </div>
              ) : (
                <div className="rounded-t-2xl bg-muted p-4">
                  <div className="flex items-center gap-3 rounded-xl bg-background p-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <IconPaperclip size={20} stroke={1.7} />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-foreground">
                        {pastedAttachment.file.name || t('ws.chat.pastedAttachmentFallbackName', locale)}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {formatAttachmentSize(pastedAttachment.file.size)}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {uploadError && (
                <div className="border-t border-border px-4 py-2 text-xs text-destructive">
                  {uploadError}
                </div>
              )}
              <DialogFooter className="rounded-b-2xl border-t border-border px-4 py-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePastedAttachmentCancel}
                  disabled={uploading}
                >
                  {t('ws.common.cancel', locale)}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handlePastedAttachmentSend()}
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
