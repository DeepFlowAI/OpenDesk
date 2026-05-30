export type OpenAgentHandoffEventType =
  | 'confirm_requested'
  | 'confirmed_by_visitor'
  | 'auto_triggered'

export function isOpenAgentHandoffEvent(metadata?: Record<string, unknown> | null): boolean {
  return metadata?.event_type === 'open_agent_handoff_event'
}

export function resolveOpenAgentHandoffEventLabel(
  metadata: Record<string, unknown> | undefined | null,
  locale: string,
): string | null {
  if (!isOpenAgentHandoffEvent(metadata)) return null

  const eventType = metadata?.handoff_event_type
  if (eventType === 'confirmed_by_visitor') {
    return locale === 'zh' ? '用户已确认转人工' : 'Visitor confirmed human handoff'
  }
  if (eventType === 'auto_triggered') {
    return locale === 'zh' ? '机器人自动触发转人工' : 'Bot auto-triggered human handoff'
  }
  return locale === 'zh' ? '请求用户确认转人工' : 'Human handoff confirmation requested'
}
