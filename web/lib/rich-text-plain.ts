/**
 * Plain-text summary for list cells and change-log snippets (rich text / HTML).
 * Markdown: lightweight whitespace-only cleanup (no full parse).
 */

function stripTagsFallback(html: string): string {
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Coerce rich text value to a single-line friendly string (table / timeline).
 */
export function richTextToPlainCell(
  value: unknown,
  typeConfig?: Record<string, unknown> | null,
): string {
  if (value == null || value === '') return ''
  const s = String(value)
  const fmt = ((typeConfig?.rich_format as string) ?? 'html').toLowerCase()
  if (fmt === 'markdown') {
    return s.replace(/\s+/g, ' ').trim()
  }
  if (typeof document !== 'undefined') {
    const d = document.createElement('div')
    d.innerHTML = s
    return (d.textContent || '').replace(/\s+/g, ' ').trim() || stripTagsFallback(s)
  }
  return stripTagsFallback(s)
}
