'use client'

import { useRef, useCallback, useState, type ChangeEvent } from 'react'
import { ComposerPrimitive } from '@assistant-ui/react'
import { useAgentChatConfig } from './agent-chat-runtime'
import { IconLoader2, IconPaperclip } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Socket } from 'socket.io-client'

type AgentComposerProps = {
  disabled: boolean
  socket: Socket | null
}

export function AgentComposer({ disabled, socket }: AgentComposerProps) {
  const { locale } = useLocaleStore()
  const { conversation, onFileSend } = useAgentChatConfig()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [uploading, setUploading] = useState(false)

  const handleTypingDebounce = useCallback(() => {
    if (typingTimerRef.current) clearTimeout(typingTimerRef.current)
    typingTimerRef.current = setTimeout(() => {
      if (socket && conversation.id) {
        socket.emit('typing', { conversation_id: conversation.id })
      }
    }, 300)
  }, [socket, conversation.id])

  const handleAttachmentSelect = useCallback(() => {
    if (uploading) return
    fileInputRef.current?.click()
  }, [uploading])

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

  if (disabled) {
    return (
      <div className="shrink-0 bg-[#FAFAFA] px-6 pb-4 pt-3">
        <div className="text-center text-sm text-muted-foreground">
          {t('ws.chat.conversationEnded', locale)}
        </div>
      </div>
    )
  }

  return (
    <div className="shrink-0 bg-[#FAFAFA] px-6 pb-4 pt-0">
      {/* 2.1 pen: input strip + card (vertical: field + toolbar) */}
      <ComposerPrimitive.Root className="flex flex-col gap-2 rounded-2xl border border-[#E5E5E5] bg-white pt-3 pb-2.5 pl-3.5 pr-3.5">
        <ComposerPrimitive.Input
          placeholder={t('ws.chat.inputPlaceholder', locale)}
          submitMode="enter"
          rows={1}
          maxRows={6}
          onChange={handleTypingDebounce}
          className="max-h-[168px] min-h-[22px] w-full resize-none border-0 bg-transparent p-0 text-sm leading-[22px] text-[#1a1a1a] outline-none ring-0 placeholder:text-[#BBBBBB] focus-visible:ring-0"
        />

        <div className="flex items-center justify-between">
          <button
            type="button"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-neutral-100 hover:text-foreground"
            onClick={handleAttachmentSelect}
            disabled={uploading}
            aria-label={t('ws.chat.attachFile', locale)}
            title={t('ws.chat.attachFile', locale)}
          >
            {uploading ? (
              <IconLoader2 size={18} stroke={1.5} className="animate-spin" />
            ) : (
              <IconPaperclip size={18} stroke={1.5} />
            )}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileChange}
          />

          <ComposerPrimitive.Send className="shrink-0 rounded-2xl bg-[#1a1a1a] px-4 py-1.5 text-[13px] font-medium leading-none text-white transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40">
            {t('ws.chat.send', locale)}
          </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </div>
  )
}
