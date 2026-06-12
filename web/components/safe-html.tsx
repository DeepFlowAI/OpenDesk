'use client'

import { useMemo } from 'react'
import type { HTMLAttributes } from 'react'
import DOMPurify from 'isomorphic-dompurify'

type SafeHtmlProps = {
  /** Untrusted HTML string (e.g. rich-text field values, channel welcome/offline messages). */
  html: string
} & Omit<HTMLAttributes<HTMLDivElement>, 'dangerouslySetInnerHTML' | 'children'>

/**
 * Renders an HTML string inside a div after sanitizing it with DOMPurify,
 * stripping scripts and event handlers while keeping rich-text markup.
 *
 * Use this instead of a raw `dangerouslySetInnerHTML` for any content that
 * originated from user or operator input.
 */
export function SafeHtml({ html, ...divProps }: SafeHtmlProps) {
  const clean = useMemo(() => DOMPurify.sanitize(html ?? ''), [html])
  return <div {...divProps} dangerouslySetInnerHTML={{ __html: clean }} />
}
