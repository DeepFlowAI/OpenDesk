export const QUEUE_ENTERED_SYSTEM_MESSAGE = '已进入人工客服队列'
export const LEGACY_QUEUE_WAITING_SYSTEM_MESSAGE = '等待客服接入...'

export function isVisitorQueueEnteredContent(content: string): boolean {
  const value = content.trim()
  return value === QUEUE_ENTERED_SYSTEM_MESSAGE || value === LEGACY_QUEUE_WAITING_SYSTEM_MESSAGE
}

export function isVisitorQueueEnteredMessage(message: {
  sender_type?: string
  content_type?: string
  content?: string
}): boolean {
  const isSystemMessage =
    message.sender_type === 'system'
    || message.content_type === 'system'
  if (!isSystemMessage) return false

  const content = typeof message.content === 'string' ? message.content : ''
  return isVisitorQueueEnteredContent(content)
}
