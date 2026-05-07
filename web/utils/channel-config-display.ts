/**
 * Hex previews for admin channel form when config stores null — matches visitor chat
 * CSS fallbacks (see message-bubble.tsx, chat-header.tsx, message-list.tsx, page.tsx).
 * Light :root tokens: web/styles/globals.css (--primary, --secondary, --muted, etc.).
 */
export const CHANNEL_COLOR_PREVIEW = {
  pageBg: '#f5f5f5',
  messageAreaBg: '#ffffff',
  headerGradient: '#343434',
  agentBubbleBg: '#f5f5f5',
  agentBubbleText: '#1f1f1f',
  userBubbleBg: '#343434',
  userBubbleText: '#fafafa',
  embedBtnBg: '#343434',
  embedBtnIcon: '#fafafa',
  sendButtonBg: '#343434',
} as const

export function channelColorPreview(stored: string | null | undefined, previewFallback: string): string {
  const trimmed = stored?.trim()
  return trimmed || previewFallback
}
