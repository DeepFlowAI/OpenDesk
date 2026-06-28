'use client'

import { useEffect, useState } from 'react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const HIDDEN_HOSTNAME = (process.env.NEXT_PUBLIC_HIDE_LEGAL_FOOTER_HOSTNAME ?? '')
  .trim()
  .toLowerCase()

interface LegalFooterProps {
  /**
   * Optional locale override. When omitted, the locale comes from the global
   * locale store. Pass this on pages that derive their own locale outside the
   * store (e.g. the public visitor chat, which reads navigator.language).
   */
  locale?: Locale
  /**
   * Single-line variant for embedded contexts where vertical space matters
   * (e.g. visitor chat). Drops the copyright line and shrinks padding.
   */
  compact?: boolean
}

/**
 * Legal footer that satisfies the AGPL-3.0 §13 obligation to offer the
 * Corresponding Source to network users. Rendered on user-facing entry pages
 * (login / forgot-password / public visitor chat); the source URL points to
 * the upstream open-source repository.
 */
export function LegalFooter({ locale: localeProp, compact = false }: LegalFooterProps = {}) {
  const { locale: storeLocale } = useLocaleStore()
  const locale = localeProp ?? storeLocale
  const [isVisible, setIsVisible] = useState(!HIDDEN_HOSTNAME)

  useEffect(() => {
    if (!HIDDEN_HOSTNAME) return
    setIsVisible(window.location.hostname.toLowerCase() !== HIDDEN_HOSTNAME)
  }, [])

  if (!isVisible) return null

  if (compact) {
    return (
      <footer className="flex items-center justify-center gap-1.5 px-4 py-1.5 text-[11px] text-muted-foreground/70">
        <span>{t('footer.license', locale)}</span>
        <a
          href="https://github.com/DeepFlowAI/OpenDesk"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-foreground"
        >
          {t('footer.source', locale)}
        </a>
      </footer>
    )
  }

  return (
    <footer className="flex flex-col items-center gap-1 px-6 py-4 text-xs text-muted-foreground">
      <span>{t('footer.copyright', locale)}</span>
      <span>
        {t('footer.license', locale)}{' '}
        <a
          href="https://github.com/DeepFlowAI/OpenDesk"
          target="_blank"
          rel="noopener noreferrer"
          className="underline hover:text-foreground"
        >
          {t('footer.source', locale)}
        </a>
      </span>
    </footer>
  )
}
