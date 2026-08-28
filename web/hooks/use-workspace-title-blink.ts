'use client'

import { useEffect, useRef, useState } from 'react'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const BLINK_INTERVAL_MS = 1500
const DEFAULT_TITLE = '工作台-OpenDesk'

type UseWorkspaceTitleBlinkOptions = {
  enabled: boolean
  unreadCount: number
  locale: Locale
}

function formatUnreadCount(count: number): string {
  return count > 99 ? '99+' : String(count)
}

function buildUnreadTitle(locale: Locale, unreadCount: number, originalTitle: string): string {
  const count = formatUnreadCount(unreadCount)
  const key = locale === 'en' && unreadCount === 1
    ? 'ws.title.unreadMessage'
    : 'ws.title.unreadMessages'

  return t(key, locale, { count, title: originalTitle })
}

function getDocumentVisible(): boolean {
  if (typeof document === 'undefined') return true
  return document.visibilityState === 'visible'
}

export function useWorkspaceTitleBlink({
  enabled,
  unreadCount,
  locale,
}: UseWorkspaceTitleBlinkOptions) {
  const originalTitleRef = useRef<string | null>(null)
  const [isDocumentVisible, setIsDocumentVisible] = useState(getDocumentVisible)

  useEffect(() => {
    if (typeof document === 'undefined') return

    const handleVisibilityChange = () => {
      setIsDocumentVisible(document.visibilityState === 'visible')
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  useEffect(() => {
    if (typeof document === 'undefined') return

    const restoreOriginalTitle = () => {
      if (originalTitleRef.current == null) return
      document.title = originalTitleRef.current
      originalTitleRef.current = null
    }

    const shouldBlink = enabled && unreadCount > 0 && !isDocumentVisible
    if (!shouldBlink) {
      restoreOriginalTitle()
      return
    }

    if (originalTitleRef.current == null) {
      originalTitleRef.current = document.title || DEFAULT_TITLE
    }

    let showUnreadTitle = true
    const applyBlinkTitle = () => {
      const originalTitle = originalTitleRef.current || DEFAULT_TITLE
      document.title = showUnreadTitle
        ? buildUnreadTitle(locale, unreadCount, originalTitle)
        : originalTitle
      showUnreadTitle = !showUnreadTitle
    }

    applyBlinkTitle()
    const intervalId = window.setInterval(applyBlinkTitle, BLINK_INTERVAL_MS)

    return () => {
      window.clearInterval(intervalId)
      restoreOriginalTitle()
    }
  }, [enabled, unreadCount, locale, isDocumentVisible])
}
