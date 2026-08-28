import type { Locale } from '@/lib/languages'

import zh from './zh/common.json'
import en from './en/common.json'
import frFR from './fr-FR/common.json'
import esES from './es-ES/common.json'
import es419 from './es-419/common.json'
import ptBR from './pt-BR/common.json'
import ptPT from './pt-PT/common.json'
import itIT from './it-IT/common.json'
import nlNL from './nl-NL/common.json'
import plPL from './pl-PL/common.json'
import ruRU from './ru-RU/common.json'
import trTR from './tr-TR/common.json'
import thTH from './th-TH/common.json'
import viVN from './vi-VN/common.json'
import idID from './id-ID/common.json'

/**
 * Flat key-value maps keyed by locale.
 * To add a new language: create `{locale}/common.json`, import it here,
 * and register it in this record.
 */
export const messages: Record<Locale, Record<string, string>> = {
  zh,
  en,
  'fr-FR': frFR,
  'es-ES': esES,
  'es-419': es419,
  'pt-BR': ptBR,
  'pt-PT': ptPT,
  'it-IT': itIT,
  'nl-NL': nlNL,
  'pl-PL': plPL,
  'ru-RU': ruRU,
  'tr-TR': trTR,
  'th-TH': thTH,
  'vi-VN': viVN,
  'id-ID': idID,
}
