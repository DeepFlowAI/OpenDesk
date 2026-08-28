/**
 * Supported UI languages. Codes `zh`/`en` are kept for backward compatibility
 * with stored data; newer languages use BCP 47 codes.
 */
export const SUPPORTED_LOCALES = [
  'zh',
  'en',
  'fr-FR',
  'es-ES',
  'es-419',
  'pt-BR',
  'pt-PT',
  'it-IT',
  'nl-NL',
  'pl-PL',
  'ru-RU',
  'tr-TR',
  'th-TH',
  'vi-VN',
  'id-ID',
] as const

export type Locale = (typeof SUPPORTED_LOCALES)[number]

export type VisitorLanguageSettings = {
  language_strategy?: 'browser' | 'fixed' | null
  default_language?: string | null
}

export const DEFAULT_LOCALE: Locale = 'zh'

/**
 * Options display the language's own local name so any user can recognize it.
 * `keywords` carries the code plus English/Chinese names so admin dropdowns
 * can search by local name, English name, Chinese name, or code.
 */
export const LANGUAGE_OPTIONS: { value: Locale; label: string; keywords: string }[] = [
  { value: 'zh', label: '中文', keywords: 'zh chinese 中文' },
  { value: 'en', label: 'English', keywords: 'en english 英语' },
  { value: 'fr-FR', label: 'Français', keywords: 'fr-fr french 法语' },
  { value: 'es-ES', label: 'Español (España)', keywords: 'es-es spanish spain 西班牙语 西班牙' },
  { value: 'es-419', label: 'Español (Latinoamérica)', keywords: 'es-419 spanish latin america 西班牙语 拉美' },
  { value: 'pt-BR', label: 'Português (Brasil)', keywords: 'pt-br portuguese brazil 葡萄牙语 巴西' },
  { value: 'pt-PT', label: 'Português (Portugal)', keywords: 'pt-pt portuguese portugal 葡萄牙语 葡萄牙' },
  { value: 'it-IT', label: 'Italiano', keywords: 'it-it italian 意大利语' },
  { value: 'nl-NL', label: 'Nederlands', keywords: 'nl-nl dutch 荷兰语' },
  { value: 'pl-PL', label: 'Polski', keywords: 'pl-pl polish 波兰语' },
  { value: 'ru-RU', label: 'Русский', keywords: 'ru-ru russian 俄语' },
  { value: 'tr-TR', label: 'Türkçe', keywords: 'tr-tr turkish 土耳其语' },
  { value: 'th-TH', label: 'ไทย', keywords: 'th-th thai 泰语' },
  { value: 'vi-VN', label: 'Tiếng Việt', keywords: 'vi-vn vietnamese 越南语' },
  { value: 'id-ID', label: 'Bahasa Indonesia', keywords: 'id-id indonesian 印尼语' },
]

/**
 * Default option per language prefix when the browser reports a region we do
 * not ship (e.g. es-MX → es-419, pt-AO → pt-BR). `in` is the legacy code for
 * Indonesian.
 */
const LANGUAGE_PREFIX_DEFAULTS: Record<string, Locale> = {
  zh: 'zh',
  en: 'en',
  fr: 'fr-FR',
  es: 'es-419',
  pt: 'pt-BR',
  it: 'it-IT',
  nl: 'nl-NL',
  pl: 'pl-PL',
  ru: 'ru-RU',
  tr: 'tr-TR',
  th: 'th-TH',
  vi: 'vi-VN',
  id: 'id-ID',
  in: 'id-ID',
}

export function isLocale(value: string | undefined | null): value is Locale {
  return Boolean(value) && (SUPPORTED_LOCALES as readonly string[]).includes(value as string)
}

/**
 * Case-insensitive match against SUPPORTED_LOCALES, returning the canonical
 * code (e.g. `PT-br` → `pt-BR`). Returns null for empty or unsupported values.
 */
export function resolveLocaleCode(value: string | undefined | null): Locale | null {
  if (!value) return null
  const normalized = value.trim().replace('_', '-').toLowerCase()
  if (!normalized) return null
  return SUPPORTED_LOCALES.find((locale) => locale.toLowerCase() === normalized) ?? null
}

/**
 * Pre-login locale detection: exact match first, then language-prefix default,
 * otherwise the given fallback (English by default for visitor-facing pages).
 */
export function detectBrowserLocale(fallback: Locale = DEFAULT_LOCALE): Locale {
  if (typeof navigator === 'undefined') return fallback
  const raw = navigator.language
  if (!raw) return fallback
  const normalized = raw.replace('_', '-').toLowerCase()
  const exact = SUPPORTED_LOCALES.find((locale) => locale.toLowerCase() === normalized)
  if (exact) return exact
  const prefix = normalized.split('-')[0]
  return LANGUAGE_PREFIX_DEFAULTS[prefix] ?? fallback
}

/**
 * Visitor chat locale: an explicit supported language or `auto` wins; otherwise
 * the channel strategy chooses browser detection or its configured language.
 */
export function resolveVisitorLocale(
  preferred?: string | null,
  settings?: VisitorLanguageSettings | null,
): Locale {
  const explicitLocale = resolveLocaleCode(preferred)
  if (explicitLocale) return explicitLocale

  const fallback = resolveLocaleCode(settings?.default_language) ?? 'en'
  if (preferred?.trim().toLowerCase() === 'auto') return detectBrowserLocale(fallback)
  if (settings?.language_strategy === 'fixed') return fallback
  return detectBrowserLocale(fallback)
}
