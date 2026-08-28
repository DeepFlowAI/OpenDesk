'use client'

import { IconAlertTriangle, IconLoader2 } from '@tabler/icons-react'

import type { Locale } from '@/context/locale-store'
import { htmlToPlainText } from '@/lib/clipboard'
import type { MessageTranslation } from '@/lib/lingomaster'
import { t } from '@/utils/i18n'

export function TranslatedMessageContent({
  content,
  isRichText,
  translation,
  locale,
}: {
  content: string
  isRichText: boolean
  translation: MessageTranslation
  locale: Locale
}) {
  const original = isRichText ? htmlToPlainText(content) : content
  const translated = translation.translated_text?.trim()

  if (translation.status !== 'translated' || !translated) {
    return (
      <div className="whitespace-pre-wrap">
        <div>{original}</div>
        {translation.status === 'pending' && (
          <div
            className="mt-2 flex items-center gap-1 border-t border-black/10 pt-2 text-xs text-[#737373]"
            role="status"
          >
            <IconLoader2 className="size-3.5 animate-spin" />
            {t('ws.chat.translation.translating', locale)}
          </div>
        )}
        {translation.status === 'failed' && (
          <div
            className="mt-2 flex items-center gap-1 border-t border-black/10 pt-2 text-xs text-amber-700"
            title={t('ws.chat.translation.failed', locale)}
          >
            <IconAlertTriangle className="size-3.5" />
            {t('ws.chat.translation.failed', locale)}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2 whitespace-pre-wrap">
      <div>
        <span className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-[#737373]">
          {t('ws.chat.translation.original', locale)}
        </span>
        <span>{original}</span>
      </div>
      <div className="border-t border-black/10 pt-2">
        <span className="mr-1.5 text-[10px] font-medium uppercase tracking-wide text-[#737373]">
          {t('ws.chat.translation.translated', locale)}
        </span>
        <span>{translated}</span>
      </div>
    </div>
  )
}
