import { describe, expect, it } from 'vitest'
import { prepareRichTextMessageHtml, richTextHasMeaningfulContent } from './rich-text-message'

describe('rich text message helpers', () => {
  it('keeps image-only rich text when the image has a sendable src', () => {
    const html = '<p><img src="https://cdn.example.com/knowledge.png" alt="knowledge"></p>'

    const prepared = prepareRichTextMessageHtml(html)

    expect(prepared).toContain('src="https://cdn.example.com/knowledge.png"')
    expect(richTextHasMeaningfulContent(prepared)).toBe(true)
  })

  it('removes images without a file id or safe source before sending', () => {
    const prepared = prepareRichTextMessageHtml('<p><img alt="missing"></p>')

    expect(prepared).not.toContain('<img')
    expect(richTextHasMeaningfulContent(prepared)).toBe(false)
  })

  it('strips temporary src from uploaded conversation images', () => {
    const prepared = prepareRichTextMessageHtml(
      '<p><img src="https://signed.example.com/source.png" data-file-id="file_123" alt="source.png"></p>',
    )

    expect(prepared).toContain('data-file-id="file_123"')
    expect(prepared).not.toContain('src=')
    expect(richTextHasMeaningfulContent(prepared)).toBe(true)
  })
})
