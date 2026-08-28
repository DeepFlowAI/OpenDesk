import { describe, expect, it } from 'vitest'
import { isImeConfirmKey } from './visitor-composer'

describe('isImeConfirmKey', () => {
  it('detects an active IME composition Enter key', () => {
    expect(isImeConfirmKey({ key: 'Enter', isComposing: true, keyCode: 13 })).toBe(true)
  })

  it('detects Safari IME confirmation by keyCode 229', () => {
    expect(isImeConfirmKey({ key: 'Enter', isComposing: false, keyCode: 229 })).toBe(true)
  })

  it('allows a regular Enter key to submit', () => {
    expect(isImeConfirmKey({ key: 'Enter', isComposing: false, keyCode: 13 })).toBe(false)
  })

  it('does not block non-Enter IME key events', () => {
    expect(isImeConfirmKey({ key: 'a', isComposing: true, keyCode: 229 })).toBe(false)
  })
})
