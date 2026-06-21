export type HandoffRouteUnavailablePayload = {
  error?: string
  reason?: string
  leave_message?: boolean
  queue_full?: boolean
  leave_message_prompt?: string
  queue_full_message?: string
  queue_full_show_leave_message_button?: boolean
  queue_full_leave_message_button_label?: string
}

export function isHandoffLeaveMessagePayload(payload: HandoffRouteUnavailablePayload): boolean {
  return payload.error === 'LEAVE_MESSAGE' || payload.leave_message === true
}

export function isHandoffQueueFullPayload(payload: HandoffRouteUnavailablePayload): boolean {
  return (
    payload.error === 'QUEUE_FULL'
    || payload.queue_full === true
    || payload.reason === 'queue_full'
  )
}
