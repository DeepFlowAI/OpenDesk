'use client'

import { useMemo } from 'react'
import type { HTMLAttributes } from 'react'

type SafeHtmlProps = {
  /** Untrusted HTML string (e.g. rich-text field values, channel welcome/offline messages). */
  html: string
} & Omit<HTMLAttributes<HTMLDivElement>, 'dangerouslySetInnerHTML' | 'children'>

/**
 * Renders an HTML string inside a div after stripping scripts and event handlers
 * while keeping safe rich-text markup.
 *
 * Use this instead of a raw `dangerouslySetInnerHTML` for any content that
 * originated from user or operator input.
 */
export function SafeHtml({ html, ...divProps }: SafeHtmlProps) {
  const clean = useMemo(() => sanitizeHtml(html ?? ''), [html])
  return <div {...divProps} dangerouslySetInnerHTML={{ __html: clean }} />
}

function sanitizeHtmlString(html: string): string {
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/\s+on[a-z]+\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, '')
    .replace(/\s+(href|src)\s*=\s*("|')\s*javascript:[\s\S]*?\2/gi, '')
    .replace(/\s+(href|src)\s*=\s*javascript:[^\s>]+/gi, '')
}

function sanitizeHtml(html: string): string {
  if (typeof document === 'undefined') return sanitizeHtmlString(html)

  const template = document.createElement('template')
  template.innerHTML = sanitizeHtmlString(html)
  template.content.querySelectorAll('script, style, iframe, object, embed').forEach((node) => node.remove())
  template.content.querySelectorAll('*').forEach((node) => {
    Array.from(node.attributes).forEach((attr) => {
      const name = attr.name.toLowerCase()
      const value = attr.value.trim().toLowerCase()
      if (name.startsWith('on')) node.removeAttribute(attr.name)
      if ((name === 'href' || name === 'src') && value.startsWith('javascript:')) {
        node.removeAttribute(attr.name)
      }
    })
  })
  return template.innerHTML
}
