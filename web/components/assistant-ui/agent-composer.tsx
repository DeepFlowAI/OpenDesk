'use client'

import {
  useEffect,
  useRef,
  useCallback,
  useState,
  type ChangeEvent,
  type ClipboardEvent as ReactClipboardEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { ComposerPrimitive, useComposerRuntime } from '@assistant-ui/react'
import { useAgentChatConfig } from './agent-chat-runtime'
import { EmojiPicker } from './emoji-picker'
import { RichTextComposer } from './rich-text-composer'
import { IconLoader2, IconLock, IconMessageCircle, IconPaperclip, IconSearch, IconStar, IconTypography } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import {
  isRichTextPlainOnly,
  prepareRichTextMessageHtml,
  richTextHasMeaningfulContent,
  richTextToPlainText,
} from '@/lib/rich-text-message'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Socket } from 'socket.io-client'

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

type AgentComposerProps = {
  disabled: boolean
  socket: Socket | null
  insertRequest?: ComposerInsertRequest | null
  inputHeight?: number
  onInputHeightCommit?: (height: number) => void
  messageSearchOpen?: boolean
  onOpenMessageSearch?: () => void
}

export type ComposerInsertRequest = {
  id: number
  text: string
}

const COMPOSER_INPUT_DEFAULT_HEIGHT = 22
const COMPOSER_INPUT_MIN_HEIGHT = 22
const COMPOSER_INPUT_MAX_HEIGHT = 168

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

function clampComposerInputHeight(height: number): number {
  return Math.min(COMPOSER_INPUT_MAX_HEIGHT, Math.max(COMPOSER_INPUT_MIN_HEIGHT, height))
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

export function AgentComposer({
  disabled,
  socket,
  insertRequest,
  inputHeight: storedInputHeight,
  onInputHeightCommit,
  messageSearchOpen = false,
  onOpenMessageSearch,
}: AgentComposerProps) {
  const { locale } = useLocaleStore()
  const composer = useComposerRuntime()
  const {
    conversation,
    onFileSend,
    satisfactionState,
    satisfactionLoading,
    satisfactionSending,
    onSendSatisfaction,
    emojiConfig,
    onRichTextImageUpload,
    onRichTextSend,
    composerMode,
    setComposerMode,
    canSendPublicReply,
    canCreateInternalNote,
    composerReadOnlyReason,
  } = useAgentChatConfig()
  const rootRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInsertIdRef = useRef<number | null>(null)
  const appliedStoredInputHeightRef = useRef<number | undefined>(undefined)
  const [uploading, setUploading] = useState(false)
  const [sentToast, setSentToast] = useState(false)
  const [inputHeight, setInputHeight] = useState(COMPOSER_INPUT_DEFAULT_HEIGHT)
  const [inputResizing, setInputResizing] = useState(false)
  const [pastedImage, setPastedImage] = useState<PastedImagePreview | null>(null)
  const [richTextMode, setRichTextMode] = useState(false)
  const [richTextDraft, setRichTextDraft] = useState('<p></p>')
  const [richTextResetKey, setRichTextResetKey] = useState(0)
  const [richTextUploading, setRichTextUploading] = useState(false)
  const [richTextSending, setRichTextSending] = useState(false)
  const showModeSwitcher = canCreateInternalNote && canSendPublicReply
  const showInternalOnlyLabel = canCreateInternalNote && !canSendPublicReply
  const isInternalMode = composerMode === 'internal'
  const showRichTextToggle =
    !isInternalMode
    && canSendPublicReply
    && String(conversation.channel?.channel_type || 'web').toLowerCase() === 'web'
  const showSatisfactionInvite =
    !isInternalMode
    && canSendPublicReply
    && satisfactionState?.disabled_reason !== 'agent_invite_disabled'
  const hasModeHeader = showModeSwitcher || showInternalOnlyLabel
  const messageSearchButton = onOpenMessageSearch ? (
    <button
      type="button"
      onClick={onOpenMessageSearch}
      className={cn(
        'flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground',
        messageSearchOpen && 'bg-neutral-100 text-foreground',
      )}
      aria-label={t('ws.chat.messageSearch.open', locale)}
      title={t('ws.chat.messageSearch.open', locale)}
    >
      <IconSearch size={16} stroke={1.7} />
    </button>
  ) : null

  useEffect(() => {
    if (typeof storedInputHeight !== 'number' || inputResizing) return
    if (storedInputHeight === appliedStoredInputHeightRef.current) return
    appliedStoredInputHeightRef.current = storedInputHeight
    setInputHeight(clampComposerInputHeight(storedInputHeight))
  }, [inputResizing, storedInputHeight])

  useEffect(() => {
    if (isInternalMode || !showRichTextToggle) setRichTextMode(false)
  }, [isInternalMode, showRichTextToggle])

  useEffect(() => {
    if (!pastedImage) return
    return () => URL.revokeObjectURL(pastedImage.previewUrl)
  }, [pastedImage])

  useEffect(() => {
    if (!insertRequest || disabled || lastInsertIdRef.current === insertRequest.id) return

    lastInsertIdRef.current = insertRequest.id
    const currentText = composer.getState().text
    const textarea =
      rootRef.current?.querySelector<HTMLTextAreaElement>('textarea[name="input"]') ??
      rootRef.current?.querySelector<HTMLTextAreaElement>('textarea')
    const hasSelection = textarea && document.activeElement === textarea
    const start = hasSelection ? textarea.selectionStart : currentText.length
    const end = hasSelection ? textarea.selectionEnd : currentText.length
    const separator = !hasSelection && currentText.trim() ? '\n\n' : ''
    const inserted = hasSelection
      ? `${currentText.slice(0, start)}${insertRequest.text}${currentText.slice(end)}`
      : `${currentText}${separator}${insertRequest.text}`
    const cursor = hasSelection ? start + insertRequest.text.length : inserted.length

    composer.setText(inserted)
    window.requestAnimationFrame(() => {
      textarea?.focus({ preventScroll: true })
      try {
        textarea?.setSelectionRange(cursor, cursor)
      } catch {
        // Ignore host selection limitations.
      }
    })
  }, [composer, disabled, insertRequest])

  const handleTypingDebounce = useCallback(() => {
    if (isInternalMode || !canSendPublicReply) return
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(() => {
      if (socket && conversation.id) {
        socket.emit('typing', { conversation_id: conversation.id })
      }
    }, 300)
  }, [socket, conversation.id, isInternalMode, canSendPublicReply])

  const handleAttachmentSelect = useCallback(() => {
    if (uploading) return
    fileInputRef.current?.click()
  }, [uploading])

  const handleSatisfactionSend = useCallback(async () => {
    const sent = await onSendSatisfaction()
    if (!sent) return
    setSentToast(true)
    window.setTimeout(() => setSentToast(false), 2200)
  }, [onSendSatisfaction])

  const handleFileChange = useCallback(
    async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      e.target.value = ''
      if (!file || uploading) return

      setUploading(true)
      try {
        await onFileSend(file)
      } catch {
        window.alert(t('ws.chat.attachmentUploadFailed', locale))
      } finally {
        setUploading(false)
      }
    },
    [locale, onFileSend, uploading],
  )

  const handlePaste = useCallback(
    (e: ReactClipboardEvent<HTMLTextAreaElement>) => {
      if (uploading || isInternalMode || !canSendPublicReply) return

      const imageFile = getClipboardImageFile(e.clipboardData)
      if (!imageFile) return

      e.preventDefault()
      setPastedImage({
        file: imageFile,
        previewUrl: URL.createObjectURL(imageFile),
      })
    },
    [canSendPublicReply, isInternalMode, uploading],
  )

  const handleRichTextToggle = useCallback(() => {
    if (!showRichTextToggle || uploading || richTextUploading || richTextSending) return

    if (!richTextMode) {
      const plainText = composer.getState().text
      if (plainText.trim()) {
        const escaped = plainText
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .split(/\n{2,}/)
          .map((part) => `<p>${part.replace(/\n/g, '<br>')}</p>`)
          .join('')
        setRichTextDraft(escaped || '<p></p>')
        composer.setText('')
      }
      setRichTextMode(true)
      return
    }

    if (richTextHasMeaningfulContent(richTextDraft) && !isRichTextPlainOnly(richTextDraft)) {
      const confirmed = window.confirm(t('ws.chat.richText.switchToPlainConfirm', locale))
      if (!confirmed) return
    }
    composer.setText(richTextToPlainText(richTextDraft))
    setRichTextMode(false)
  }, [composer, locale, richTextDraft, richTextMode, richTextSending, richTextUploading, showRichTextToggle, uploading])

  const handleRichTextSend = useCallback(
    async (html: string) => {
      const content = prepareRichTextMessageHtml(html)
      if (!richTextHasMeaningfulContent(content) || richTextUploading || richTextSending) return

      setRichTextSending(true)
      try {
        await onRichTextSend(content)
        setRichTextDraft('<p></p>')
        setRichTextResetKey((key) => key + 1)
      } catch {
        window.alert(t('ws.chat.richText.sendFailed', locale))
      } finally {
        setRichTextSending(false)
      }
    },
    [locale, onRichTextSend, richTextSending, richTextUploading],
  )

  const handlePastedImageCancel = useCallback(() => {
    if (uploading) return
    setPastedImage(null)
  }, [uploading])

  const handlePastedImageSend = useCallback(async () => {
    if (!pastedImage || uploading) return

    setUploading(true)
    try {
      await onFileSend(pastedImage.file)
      setPastedImage(null)
    } catch {
      window.alert(t('ws.chat.attachmentUploadFailed', locale))
    } finally {
      setUploading(false)
    }
  }, [locale, onFileSend, pastedImage, uploading])

  const resizeInputBy = useCallback((delta: number) => {
    setInputHeight((height) => {
      const nextHeight = clampComposerInputHeight(height + delta)
      onInputHeightCommit?.(nextHeight)
      return nextHeight
    })
  }, [onInputHeightCommit])

  const handleInputResizeStart = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return

      event.preventDefault()
      const startY = event.clientY
      const startHeight = inputHeight
      let nextHeight = startHeight

      setInputResizing(true)

      const handlePointerMove = (moveEvent: PointerEvent) => {
        moveEvent.preventDefault()
        nextHeight = clampComposerInputHeight(startHeight + startY - moveEvent.clientY)
        setInputHeight(nextHeight)
      }

      const stopResize = () => {
        setInputResizing(false)
        onInputHeightCommit?.(nextHeight)
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', stopResize)
        window.removeEventListener('pointercancel', stopResize)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', stopResize)
      window.addEventListener('pointercancel', stopResize)
    },
    [inputHeight, onInputHeightCommit],
  )

  const handleInputResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'ArrowUp') {
        event.preventDefault()
        resizeInputBy(22)
      } else if (event.key === 'ArrowDown') {
        event.preventDefault()
        resizeInputBy(-22)
      } else if (event.key === 'Home') {
        event.preventDefault()
        setInputHeight(COMPOSER_INPUT_MIN_HEIGHT)
        onInputHeightCommit?.(COMPOSER_INPUT_MIN_HEIGHT)
      } else if (event.key === 'End') {
        event.preventDefault()
        setInputHeight(COMPOSER_INPUT_MAX_HEIGHT)
        onInputHeightCommit?.(COMPOSER_INPUT_MAX_HEIGHT)
      }
    },
    [onInputHeightCommit, resizeInputBy],
  )

  useEffect(() => {
    if (!inputResizing) return

    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'row-resize'
    document.body.style.userSelect = 'none'

    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }
  }, [inputResizing])

  if (disabled) {
    return (
      <div className="shrink-0 bg-[#FAFAFA] px-6 pb-4 pt-3">
        <div className="rounded-xl border border-[#E5E5E5] bg-white px-4 py-3 text-center text-sm text-muted-foreground">
          {t('ws.chat.historyReadOnlyHint', locale)}
        </div>
      </div>
    )
  }

  if (composerReadOnlyReason) {
    return (
      <div className="shrink-0 bg-[#FAFAFA] px-6 pb-4 pt-3">
        <div className="rounded-xl border border-[#E5E5E5] bg-white px-4 py-3 text-center text-sm text-muted-foreground">
          {composerReadOnlyReason}
        </div>
      </div>
    )
  }

  return (
    <div ref={rootRef} className="relative shrink-0 bg-[#FAFAFA] px-6 pb-4 pt-0">
      {sentToast && (
        <div className="pointer-events-none absolute left-1/2 top-[-38px] z-10 -translate-x-1/2 rounded-full bg-[#1a1a1a] px-3 py-1.5 text-xs font-medium text-white shadow-lg">
          {t('ws.chat.satisfactionSent', locale)}
        </div>
      )}
      {/* 2.1 pen: input strip + card (vertical: field + toolbar) */}
      <div
        role="separator"
        aria-label={locale === 'zh' ? '调整输入框高度' : 'Resize composer input'}
        aria-orientation="horizontal"
        aria-valuemin={COMPOSER_INPUT_MIN_HEIGHT}
        aria-valuemax={COMPOSER_INPUT_MAX_HEIGHT}
        aria-valuenow={inputHeight}
        tabIndex={0}
        onPointerDown={handleInputResizeStart}
        onKeyDown={handleInputResizeKeyDown}
        className="absolute left-6 right-6 top-[-1px] z-10 h-3 cursor-row-resize touch-none outline-none"
      />
      <ComposerPrimitive.Root
        className={cn(
          'relative flex flex-col gap-2 rounded-2xl border pt-3 pb-2.5 pl-3.5 pr-3.5 transition-colors',
          isInternalMode ? 'border-[#EDE0C4] bg-[#FFF8E7]' : 'border-[#E5E5E5] bg-white',
        )}
      >
        {messageSearchButton && !hasModeHeader && (
          <div className="absolute right-3.5 top-2.5 z-10">
            {messageSearchButton}
          </div>
        )}
        {hasModeHeader && (
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-2">
              {showModeSwitcher ? (
                <div className="inline-flex shrink-0 rounded-lg bg-[#F0F0F0] p-1">
                  <button
                    type="button"
                    onClick={() => setComposerMode('public')}
                    className={cn(
                      'flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium transition-colors',
                      composerMode === 'public' ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#737373]',
                    )}
                  >
                    <IconMessageCircle size={14} stroke={1.7} />
                    {t('ws.chat.publicReply', locale)}
                  </button>
                  <button
                    type="button"
                    onClick={() => setComposerMode('internal')}
                    className={cn(
                      'flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium transition-colors',
                      composerMode === 'internal' ? 'bg-white/90 text-[#1a1a1a] shadow-sm' : 'text-[#737373]',
                    )}
                  >
                    <IconLock size={14} stroke={1.7} />
                    {t('ws.chat.internalNote', locale)}
                  </button>
                </div>
              ) : (
                <div className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-[#F0F0F0] px-2 text-[12px] font-medium text-[#737373]">
                  <IconLock size={14} stroke={1.7} />
                  {t('ws.chat.internalNote', locale)}
                </div>
              )}
              {isInternalMode && (
                <span className="truncate text-[11px] text-[#999999]">
                  {t('ws.chat.internalNoteHint', locale)}
                </span>
              )}
            </div>
            {messageSearchButton}
          </div>
        )}
        {richTextMode ? (
          <RichTextComposer
            key={richTextResetKey}
            value={richTextDraft}
            disabled={richTextSending}
            uploading={richTextUploading}
            locale={locale}
            editorHeight={inputHeight}
            editorMaxHeight={COMPOSER_INPUT_MAX_HEIGHT}
            onChange={setRichTextDraft}
            onImageUpload={onRichTextImageUpload}
            onUploadingChange={setRichTextUploading}
            emojiConfig={emojiConfig}
          />
        ) : (
          <ComposerPrimitive.Input
            asChild
            placeholder={isInternalMode ? t('ws.chat.internalNotePlaceholder', locale) : t('ws.chat.inputPlaceholder', locale)}
            submitMode="enter"
            rows={1}
            onChange={handleTypingDebounce}
            onPaste={handlePaste}
            className={cn(
              'max-h-[168px] min-h-[22px] w-full resize-none overflow-y-auto border-0 bg-transparent p-0 text-sm leading-[22px] text-[#1a1a1a] outline-none ring-0 focus-visible:ring-0',
              messageSearchButton && !hasModeHeader && 'pr-9',
              isInternalMode ? 'placeholder:text-[#B8956A]' : 'placeholder:text-[#BBBBBB]',
            )}
            style={{ height: inputHeight }}
          >
            <textarea />
          </ComposerPrimitive.Input>
        )}

        <div className="flex items-center justify-between">
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground"
            onClick={handleAttachmentSelect}
            disabled={uploading || isInternalMode || !canSendPublicReply}
            aria-label={t('ws.chat.attachFile', locale)}
            title={isInternalMode ? t('ws.chat.internalAttachmentDisabled', locale) : t('ws.chat.attachFile', locale)}
          >
            {uploading ? (
              <IconLoader2 size={18} stroke={1.5} className="animate-spin" />
            ) : (
              <IconPaperclip size={18} stroke={1.5} />
            )}
          </button>
          {showSatisfactionInvite && (
            <button
              type="button"
              className="ml-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              onClick={handleSatisfactionSend}
              disabled={satisfactionLoading || satisfactionSending || !satisfactionState?.can_invite}
              aria-label={t('ws.chat.satisfactionSend', locale)}
              title={
                satisfactionState?.can_invite
                  ? t('ws.chat.satisfactionSend', locale)
                  : t(`ws.chat.satisfactionDisabled.${satisfactionState?.disabled_reason || 'unknown'}`, locale)
              }
            >
              {satisfactionSending ? (
                <IconLoader2 size={18} stroke={1.5} className="animate-spin" />
              ) : (
                <IconStar size={18} stroke={1.5} />
              )}
            </button>
          )}
          <EmojiPicker config={emojiConfig} locale={locale} disabled={richTextMode} />
          {showRichTextToggle && (
            <button
              type="button"
              className={cn(
                'ml-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40',
                richTextMode && 'bg-neutral-100 text-foreground',
              )}
              onClick={handleRichTextToggle}
              disabled={uploading || richTextUploading || richTextSending}
              aria-label={t('ws.chat.richText.toggle', locale)}
              title={t('ws.chat.richText.toggle', locale)}
            >
              <IconTypography size={18} stroke={1.5} />
            </button>
          )}
          {/* Hit target between attachment and send: empty flex gap did not focus the textarea */}
          <div
            role="presentation"
            className="min-h-8 flex-1 cursor-text self-stretch"
            onPointerDown={(e) => {
              if (e.button !== 0) return
              focusComposerTextarea(e)
            }}
          />
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />

          {richTextMode ? (
            <button
              type="button"
              className="shrink-0 rounded-2xl bg-[#1a1a1a] px-4 py-1.5 text-[13px] font-medium leading-none text-white transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
              onClick={() => void handleRichTextSend(richTextDraft)}
              disabled={!richTextHasMeaningfulContent(richTextDraft) || richTextUploading || richTextSending}
            >
              {richTextSending ? t('ws.chat.richText.sending', locale) : t('ws.chat.send', locale)}
            </button>
          ) : (
            <ComposerPrimitive.Send className="shrink-0 rounded-2xl bg-[#1a1a1a] px-4 py-1.5 text-[13px] font-medium leading-none text-white transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40">
              {t('ws.chat.send', locale)}
            </ComposerPrimitive.Send>
          )}
        </div>
      </ComposerPrimitive.Root>
      <Dialog open={pastedImage != null} onOpenChange={(open) => !open && handlePastedImageCancel()}>
        <DialogContent
          className="w-[520px] max-w-[calc(100vw-2rem)] gap-0 overflow-hidden rounded-2xl border border-[#E5E5E5] bg-white p-0 shadow-lg ring-0"
          showCloseButton={false}
        >
          <DialogTitle className="sr-only">{t('ws.chat.pastedImagePreviewTitle', locale)}</DialogTitle>
          {pastedImage && (
            <>
              <div className="max-h-[70vh] overflow-hidden rounded-t-2xl bg-[#F5F5F5] p-4">
                <img
                  src={pastedImage.previewUrl}
                  alt={t('ws.chat.pastedImagePreviewAlt', locale)}
                  className="max-h-[60vh] w-full rounded-xl bg-white object-contain"
                />
              </div>
              <DialogFooter className="rounded-b-2xl border-t border-[#E5E5E5] px-4 py-3">
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
