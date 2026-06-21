type OfflineMessageEventLike = {
  metadata?: Record<string, unknown> | null
}

export const LEAVE_MESSAGE_PROMPT_EVENT = 'leave_message_prompt'

export function isLeaveMessagePromptMessage(message: OfflineMessageEventLike): boolean {
  return message.metadata?.offline_message_event === LEAVE_MESSAGE_PROMPT_EVENT
}

// Mirror the server-side `_html_to_plain_text` so the client-rendered leave
// message prompt looks identical to the prompt the server persists once the
// first message creates the offline message record. This avoids a visible
// swap (rich HTML preview -> plain-text server message) when the record is
// created.
export function leaveMessagePromptToPlainText(html: string): string {
  if (!html) return ''
  let text = html.replace(/<[^>]*>/g, ' ')
  if (typeof document !== 'undefined') {
    const el = document.createElement('textarea')
    el.innerHTML = text
    text = el.value
  } else {
    text = text
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
  }
  return text.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim()
}
