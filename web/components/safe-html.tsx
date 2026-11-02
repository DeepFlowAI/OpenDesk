'use client'

import DOMPurify from 'isomorphic-dompurify'
import { useMemo } from 'react'
import type { HTMLAttributes } from 'react'

type SafeHtmlProps = {
  /** Untrusted HTML string (e.g. rich-text field values, channel welcome/offline messages). */
  html: string
} & Omit<HTMLAttributes<HTMLDivElement>, 'dangerouslySetInnerHTML' | 'children'>

/**
 * Renders an HTML string inside a div after sanitizing it with DOMPurify,
 * keeping safe rich-text markup.
 *
 * Use this instead of a raw `dangerouslySetInnerHTML` for any content that
 * originated from user or operator input.
 */
export function SafeHtml({ html, ...divProps }: SafeHtmlProps) {
  const clean = useMemo(() => sanitizeHtml(html ?? ''), [html])
  return <div {...divProps} dangerouslySetInnerHTML={{ __html: clean }} />
}

// DOMPurify's default URI allowlist plus `blob:`, which the composer uses for
// local image previews before upload.
const ALLOWED_URI_REGEXP =
  /^(?:(?:(?:f|ht)tps?|mailto|tel|callto|sms|cid|xmpp|matrix|blob):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i

const SANITIZE_CONFIG = {
  ADD_ATTR: ['target'],
  FORBID_TAGS: ['style', 'form', 'iframe', 'object', 'embed'],
  ALLOWED_URI_REGEXP,
}

let hooksInstalled = false

function installHooks() {
  if (hooksInstalled) return
  hooksInstalled = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A' && node.getAttribute('target') === '_blank') {
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
}

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  installHooks()
  return DOMPurify.sanitize(html, SANITIZE_CONFIG)
}
