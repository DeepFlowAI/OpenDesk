import { describe, expect, it } from 'vitest'
import {
  buildRichTextDisplayHtml,
  isUsableRichTextImageSrc,
} from './rich-text-message-content'

describe('isUsableRichTextImageSrc', () => {
  it('rejects loading sentinels and placeholder gif', () => {
    expect(isUsableRichTextImageSrc('loading')).toBe(false)
    expect(isUsableRichTextImageSrc('failed')).toBe(false)
    expect(isUsableRichTextImageSrc('data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')).toBe(false)
    expect(isUsableRichTextImageSrc('')).toBe(false)
    expect(isUsableRichTextImageSrc(null)).toBe(false)
  })

  it('accepts http(s) and blob urls', () => {
    expect(isUsableRichTextImageSrc('https://cdn.example.com/a.png')).toBe(true)
    expect(isUsableRichTextImageSrc('http://cdn.example.com/a.png')).toBe(true)
    expect(isUsableRichTextImageSrc('blob:https://example.com/uuid')).toBe(true)
  })
})

describe('buildRichTextDisplayHtml', () => {
  it('keeps loading sentinel as loading placeholder instead of src=loading', () => {
    const html = '<p><img data-file-id="file_1" alt="a.png"></p>'
    const rendered = buildRichTextDisplayHtml(html, { file_1: 'loading' })
    const template = document.createElement('template')
    template.innerHTML = rendered
    const img = template.content.querySelector('img')
    expect(img?.getAttribute('data-rich-text-loading')).toBe('true')
    expect(img?.getAttribute('src')).not.toBe('loading')
    expect(img?.hasAttribute('data-file-id')).toBe(true)
  })

  it('applies resolved urls and clears loading flags', () => {
    const html = '<p><img data-file-id="file_1" alt="a.png"></p>'
    const rendered = buildRichTextDisplayHtml(html, {
      file_1: 'https://cdn.example.com/a.png',
    })
    const template = document.createElement('template')
    template.innerHTML = rendered
    const img = template.content.querySelector('img')
    expect(img?.getAttribute('src')).toBe('https://cdn.example.com/a.png')
    expect(img?.hasAttribute('data-rich-text-loading')).toBe(false)
    expect(img?.hasAttribute('data-rich-text-load-failed')).toBe(false)
  })
})
