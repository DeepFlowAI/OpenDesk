export const RICH_TEXT_IMAGE_PLACEHOLDER_ZH = '[图片]'
export const RICH_TEXT_IMAGE_PLACEHOLDER_EN = '[Image]'

function parseHtml(html: string): Document | null {
  if (typeof window === 'undefined' || typeof DOMParser === 'undefined') return null
  return new DOMParser().parseFromString(html, 'text/html')
}

function stripHtmlFallback(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function richTextToPlainText(html: string): string {
  const doc = parseHtml(html)
  if (!doc) return stripHtmlFallback(html)
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim()
}

export function richTextHasMeaningfulContent(html: string): boolean {
  const doc = parseHtml(html)
  if (!doc) return Boolean(stripHtmlFallback(html) || /<img\b/i.test(html))
  return Boolean((doc.body.textContent || '').trim() || doc.body.querySelector('img'))
}

export function isRichTextPlainOnly(html: string): boolean {
  const doc = parseHtml(html)
  if (!doc) return !/(<(img|h[1-6]|ul|ol|li|blockquote|a|strong|b|em|i)\b|<span\b[^>]*\bstyle\s*=\s*["'][^"']*color\s*:)/i.test(html)
  return !doc.body.querySelector('img,h1,h2,h3,h4,h5,h6,ul,ol,blockquote,a,strong,b,em,i,span[style*="color"]')
}

export function prepareRichTextMessageHtml(html: string): string {
  const doc = parseHtml(html)
  if (!doc) return html

  doc.body.querySelectorAll('img').forEach((img) => {
    if (!img.getAttribute('data-file-id')) {
      img.remove()
      return
    }
    img.removeAttribute('src')
  })

  return doc.body.innerHTML.trim()
}

export function richTextPreview(html: string, locale: 'zh' | 'en'): string {
  const text = richTextToPlainText(html)
  if (text) return text
  return /<img\b/i.test(html)
    ? (locale === 'zh' ? RICH_TEXT_IMAGE_PLACEHOLDER_ZH : RICH_TEXT_IMAGE_PLACEHOLDER_EN)
    : ''
}
