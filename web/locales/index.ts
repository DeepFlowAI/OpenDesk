import type { Locale } from '@/context/locale-store'

import zh from './zh/common.json'
import en from './en/common.json'

/**
 * Flat key-value maps keyed by locale.
 * To add a new language: create `{locale}/common.json`, import it here,
 * and register it in this record.
 */
export const messages: Record<Locale, Record<string, string>> = {
  zh,
  en,
}
