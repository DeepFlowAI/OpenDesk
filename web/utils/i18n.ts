import type { Locale } from '@/context/locale-store'
import { messages } from '@/locales'

export function t(key: string, locale: Locale, params?: Record<string, string | number>): string {
  let text = messages[locale]?.[key] ?? key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v))
    }
  }
  return text
}
