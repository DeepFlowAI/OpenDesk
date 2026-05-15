import { pinyin } from 'pinyin-pro'

export const FIELD_KEY_PATTERN = /^[a-z_][a-z0-9_]{1,63}$/

export function generateFieldKey(name: string): string {
  const pinyinResult = pinyin(name, { toneType: 'none', type: 'array' })
  const transliterated = Array.isArray(pinyinResult) ? pinyinResult.join('_') : pinyinResult
  let key = transliterated
    .normalize('NFKD')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase()

  if (/^[0-9]/.test(key)) {
    key = `field_${key}`
  }

  return key.slice(0, 64).replace(/_+$/g, '')
}

export function isFieldKeyValid(key: string): boolean {
  return FIELD_KEY_PATTERN.test(key)
}
