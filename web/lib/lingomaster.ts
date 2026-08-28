import type { MessageMetadata } from '@/models/conversation'

export type MessageTranslation = {
  status: 'pending' | 'translated' | 'failed'
  source_language: string
  target_language: string
  translated_text?: string
  direction: 'visitor_to_agent' | 'agent_to_visitor'
}

export const TRANSLATION_LANGUAGES = [
  { code: 'zh', label: '中文' },
  { code: 'en', label: 'English' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'fr-FR', label: 'Français' },
  { code: 'es-419', label: 'Español' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt-BR', label: 'Português' },
  { code: 'it-IT', label: 'Italiano' },
  { code: 'nl-NL', label: 'Nederlands' },
  { code: 'pl-PL', label: 'Polski' },
  { code: 'ru-RU', label: 'Русский' },
  { code: 'tr-TR', label: 'Türkçe' },
  { code: 'th-TH', label: 'ไทย' },
  { code: 'vi-VN', label: 'Tiếng Việt' },
  { code: 'id-ID', label: 'Bahasa Indonesia' },
] as const

export function languageLabel(code: string | null | undefined): string {
  if (!code) return '—'
  const primary = code.toLowerCase().split('-')[0]
  const match = TRANSLATION_LANGUAGES.find((language) => (
    language.code.toLowerCase() === code.toLowerCase()
    || language.code.toLowerCase().split('-')[0] === primary
  ))
  return match?.label ?? primary.toUpperCase()
}

export function getMessageTranslation(metadata?: MessageMetadata): MessageTranslation | null {
  const value = metadata?.translation
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  if (!['pending', 'translated', 'failed'].includes(String(record.status))) return null
  if (typeof record.source_language !== 'string' || typeof record.target_language !== 'string') return null
  if (!['visitor_to_agent', 'agent_to_visitor'].includes(String(record.direction))) return null
  if (record.translated_text != null && typeof record.translated_text !== 'string') return null
  return record as MessageTranslation
}
