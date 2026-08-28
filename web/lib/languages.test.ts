import { afterEach, describe, expect, it, vi } from 'vitest'

import { resolveVisitorLocale } from './languages'

function setBrowserLanguage(language: string) {
  vi.spyOn(window.navigator, 'language', 'get').mockReturnValue(language)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('visitor locale resolution', () => {
  it('gives an explicit supported locale highest priority', () => {
    setBrowserLanguage('zh-CN')

    expect(resolveVisitorLocale('PT-br', {
      language_strategy: 'fixed',
      default_language: 'fr-FR',
    })).toBe('pt-BR')
  })

  it('lets explicit auto override a fixed channel strategy', () => {
    setBrowserLanguage('es-MX')

    expect(resolveVisitorLocale('auto', {
      language_strategy: 'fixed',
      default_language: 'fr-FR',
    })).toBe('es-419')
  })

  it('uses the configured language for a fixed channel strategy', () => {
    setBrowserLanguage('zh-CN')

    expect(resolveVisitorLocale(null, {
      language_strategy: 'fixed',
      default_language: 'vi-VN',
    })).toBe('vi-VN')
  })

  it('uses the channel default when browser language is unsupported', () => {
    setBrowserLanguage('de-DE')

    expect(resolveVisitorLocale(null, {
      language_strategy: 'browser',
      default_language: 'fr-FR',
    })).toBe('fr-FR')
  })

  it('treats an invalid explicit locale as absent', () => {
    setBrowserLanguage('zh-CN')

    expect(resolveVisitorLocale('de-DE', {
      language_strategy: 'fixed',
      default_language: 'it-IT',
    })).toBe('it-IT')
  })

  it('falls back to browser detection and English for legacy settings', () => {
    setBrowserLanguage('de-DE')

    expect(resolveVisitorLocale()).toBe('en')
  })
})
