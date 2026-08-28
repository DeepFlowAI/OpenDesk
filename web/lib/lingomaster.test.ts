import { describe, expect, it } from 'vitest'

import { getMessageTranslation, languageLabel } from '@/lib/lingomaster'

describe('LingoMaster helpers', () => {
  it('uses local language names and ISO fallback', () => {
    expect(languageLabel('es-ES')).toBe('Español')
    expect(languageLabel('ja')).toBe('日本語')
    expect(languageLabel('sv')).toBe('SV')
  })

  it('parses valid translation metadata', () => {
    expect(getMessageTranslation({
      translation: {
        status: 'translated',
        source_language: 'ja',
        target_language: 'zh',
        translated_text: '你好',
        direction: 'visitor_to_agent',
      },
    })?.translated_text).toBe('你好')
  })

  it('rejects invalid metadata', () => {
    expect(getMessageTranslation({ translation: { status: 'unknown' } })).toBeNull()
  })
})
