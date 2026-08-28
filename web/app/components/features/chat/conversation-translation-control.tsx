'use client'

import { useEffect, useRef, useState } from 'react'
import { IconChevronDown, IconLanguage } from '@tabler/icons-react'
import type { Socket } from 'socket.io-client'

import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { languageLabel, TRANSLATION_LANGUAGES } from '@/lib/lingomaster'
import type { ConversationTranslationSettings } from '@/models/lingomaster'
import {
  lingomasterKeys,
  useConversationTranslationSettings,
  useUpdateConversationTranslationSettings,
} from '@/service/use-lingomaster'
import { useQueryClient } from '@tanstack/react-query'
import { t } from '@/utils/i18n'

type TranslationSettingsUpdatedEvent = {
  conversation_id: number
  settings: ConversationTranslationSettings
}

export function ConversationTranslationControl({
  conversationId,
  canManage,
  socket,
}: {
  conversationId: number
  canManage: boolean
  socket: Socket | null
}) {
  const { locale } = useLocaleStore()
  const queryClient = useQueryClient()
  const query = useConversationTranslationSettings(conversationId)
  const update = useUpdateConversationTranslationSettings(conversationId)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const settings = query.data
  const currentLanguageInCatalog = Boolean(settings?.visitor_language && TRANSLATION_LANGUAGES.some(
    (language) => language.code.toLowerCase() === settings.visitor_language?.toLowerCase(),
  ))

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  useEffect(() => {
    if (!socket) return
    const sync = (event: TranslationSettingsUpdatedEvent) => {
      if (event.conversation_id !== conversationId) return
      queryClient.setQueryData(lingomasterKeys.conversation(conversationId), event.settings)
    }
    socket.on('translation_settings_updated', sync)
    return () => {
      socket.off('translation_settings_updated', sync)
    }
  }, [conversationId, queryClient, socket])

  if (query.isError || !settings?.global_enabled) return null

  const disabled = !settings?.global_enabled || !canManage || update.isPending
  const sourceLabel = settings?.visitor_language
    ? languageLabel(settings.visitor_language)
    : t('ws.chat.visitorWebStatusUnknown', locale)

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        className={cn(
          'flex h-7 items-center gap-1 rounded-md border border-[#E5E5E5] bg-white px-2 text-[12px] text-[#555555] hover:bg-[#F5F5F5]',
          query.isLoading && 'animate-pulse',
        )}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <IconLanguage className="size-3.5" />
        <span>{sourceLabel}</span>
        {settings?.global_enabled && !settings.agent_translation_enabled && (
          <span className="rounded bg-amber-50 px-1 py-0.5 text-[10px] text-amber-700">
            {t('ws.chat.translation.outgoingDisabled', locale)}
          </span>
        )}
        <IconChevronDown className="size-3" />
      </button>

      {open && settings && (
        <div className="absolute left-0 top-9 z-50 w-80 rounded-lg border border-border bg-background p-4 text-sm shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <div className="font-semibold text-foreground">{t('ws.chat.translation.settingsTitle', locale)}</div>
            {!settings.global_enabled && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {t('ws.chat.translation.globalDisabled', locale)}
              </span>
            )}
          </div>

          <label className="block space-y-1.5">
            <span className="text-xs text-muted-foreground">{t('ws.chat.translation.visitorLanguage', locale)}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring"
              disabled={disabled}
              value={settings.visitor_language_locked && settings.visitor_language ? settings.visitor_language : 'auto'}
              onChange={(event) => {
                const value = event.target.value
                update.mutate(value === 'auto'
                  ? { visitor_language_mode: 'auto' }
                  : { visitor_language_mode: 'manual', visitor_language: value })
              }}
            >
              <option value="auto">{t('ws.chat.translation.auto', locale)}</option>
              {settings.visitor_language && !currentLanguageInCatalog && (
                <option value={settings.visitor_language}>{languageLabel(settings.visitor_language)}</option>
              )}
              {TRANSLATION_LANGUAGES.map((language) => (
                <option key={language.code} value={language.code}>{language.label}</option>
              ))}
            </select>
          </label>

          <div className="mt-4 space-y-3 border-t border-border pt-4">
            <label className="flex items-center justify-between gap-4">
              <span>{t('ws.chat.translation.visitorIncoming', locale)}</span>
              <Switch
                checked={settings.visitor_translation_enabled}
                disabled={disabled}
                onCheckedChange={(value) => update.mutate({ visitor_translation_enabled: value })}
              />
            </label>
            <label className="flex items-center justify-between gap-4">
              <span>{t('ws.chat.translation.agentOutgoing', locale)}</span>
              <Switch
                checked={settings.agent_translation_enabled}
                disabled={disabled}
                onCheckedChange={(value) => update.mutate({ agent_translation_enabled: value })}
              />
            </label>
            <button
              type="button"
              className="text-xs font-medium text-foreground underline-offset-4 hover:underline disabled:opacity-50"
              disabled={disabled || (!settings.visitor_translation_enabled && !settings.agent_translation_enabled)}
              onClick={() => update.mutate({
                visitor_translation_enabled: false,
                agent_translation_enabled: false,
              })}
            >
              {t('ws.chat.translation.disableAll', locale)}
            </button>
          </div>

          <label className="mt-4 block space-y-1.5 border-t border-border pt-4">
            <span className="text-xs text-muted-foreground">{t('ws.chat.translation.incomingTarget', locale)}</span>
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring"
              disabled={disabled}
              value={settings.visitor_target_mode === 'fixed' && settings.visitor_target_language
                ? settings.visitor_target_language
                : 'agent'}
              onChange={(event) => {
                const value = event.target.value
                update.mutate(value === 'agent'
                  ? { visitor_target_mode: 'agent' }
                  : { visitor_target_mode: 'fixed', visitor_target_language: value })
              }}
            >
              <option value="agent">
                {t('ws.chat.translation.followAgent', locale, { language: languageLabel(settings.agent_language) })}
              </option>
              {TRANSLATION_LANGUAGES.map((language) => (
                <option key={language.code} value={language.code}>{language.label}</option>
              ))}
            </select>
          </label>

          {!canManage && (
            <p className="mt-3 text-xs text-muted-foreground">{t('ws.chat.translation.readOnly', locale)}</p>
          )}
        </div>
      )}
    </div>
  )
}
