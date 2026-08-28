import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import { resolveLocaleCode, DEFAULT_LOCALE } from '@/lib/languages'
import { singleAvatarLetter } from '@/lib/avatar-fallback'

const SATISFACTION_INVITE_ZH = /^.+发送了满意度邀请$/
const SATISFACTION_SUBMITTED_ZH = '访客提交了满意度评价'
export const SESSION_TRANSFER_EVENT_TYPE = 'session_transfer'
export const COLLABORATOR_JOINED_EVENT_TYPE = 'collaborator_joined'

const VISITOR_SYSTEM_EVENT_KEYS: Record<string, string> = {
  open_agent_bot_started: 'chat.system.botStarted',
  agent_assigned: 'chat.system.agentJoined',
  open_agent_handoff_success: 'chat.system.agentJoined',
  conversation_started: 'chat.system.conversationStarted',
  new_conversation_from_history: 'chat.system.conversationStarted',
  conversation_ended: 'chat.ended',
  invitation_sent: 'ws.chat.event.satisfactionInvited',
  feedback_submitted: 'ws.chat.event.satisfactionSubmitted',
  offline_message_conversation_created: 'chat.offlineReply.connected',
  queue_entered: 'chat.queue.entered',
}

const VISITOR_LEGACY_SYSTEM_CONTENT_KEYS: Record<string, string> = {
  '智能助手开始接待': 'chat.system.botStarted',
  '客服已接入会话': 'chat.system.agentJoined',
  '已为您转接人工客服': 'chat.system.agentJoined',
  '用户发起了新会话': 'chat.system.conversationStarted',
  '客服发起了新会话': 'chat.system.conversationStarted',
  '客服已结束会话': 'chat.ended',
  '用户已结束会话': 'chat.ended',
  '客服已基于留言创建会话': 'chat.offlineReply.connected',
  '访客提交了满意度评价': 'ws.chat.event.satisfactionSubmitted',
  '已进入人工客服队列': 'chat.queue.entered',
  '等待客服接入...': 'chat.queue.entered',
  '当前人工客服不在线，您可以继续向智能助手咨询': 'chat.handoff.unavailableKeepChatting',
  '当前人工客服繁忙，您可以继续向智能助手咨询': 'chat.handoff.unavailableKeepChatting',
}

function normalizeLocale(locale: string): Locale {
  return resolveLocaleCode(locale) ?? DEFAULT_LOCALE
}

function isSessionTransferMetadata(metadata: Record<string, unknown> | undefined): boolean {
  return metadata?.event_type === SESSION_TRANSFER_EVENT_TYPE
}

function isCollaboratorJoinedMetadata(metadata: Record<string, unknown> | undefined): boolean {
  return metadata?.event_type === COLLABORATOR_JOINED_EVENT_TYPE
}

/** Workspace transfer audit copy uses legal employee names. */
export function resolveWorkspaceSessionTransferContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: string,
): string | null {
  if (!isSessionTransferMetadata(metadata)) return null
  const from = metadata?.from_agent_name
  const to = metadata?.to_agent_name
  if (typeof from !== 'string' || typeof to !== 'string' || !from || !to) return null
  return t('ws.chat.event.sessionTransferredDetail', normalizeLocale(locale), { from, to })
}

/** Visitor transfer audit copy uses employee nicknames. */
export function resolveVisitorSessionTransferContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: string,
): string | null {
  if (!isSessionTransferMetadata(metadata)) return null
  const from = metadata?.from_agent_nickname
  const to = metadata?.to_agent_nickname
  if (typeof from !== 'string' || typeof to !== 'string' || !from || !to) return null
  return t('ws.chat.event.sessionTransferredDetail', normalizeLocale(locale), { from, to })
}

export function resolveVisitorCollaboratorJoinedContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: string,
): string | null {
  if (!isCollaboratorJoinedMetadata(metadata)) return null
  const name = metadata?.collaborator_nickname
  if (typeof name !== 'string' || !name.trim()) return null
  return t('ws.chat.event.collaboratorJoinedDetail', normalizeLocale(locale), { name: name.trim() })
}

/** Strip human agent names from satisfaction event copy in workspace views. */
export function sanitizeWorkspaceAgentEventContent(content: string, locale: string): string {
  const trimmed = content.trim()
  const safeLocale = normalizeLocale(locale)
  if (!trimmed) return content
  if (SATISFACTION_INVITE_ZH.test(trimmed)) {
    return t('ws.chat.event.satisfactionInvited', safeLocale)
  }
  if (trimmed === SATISFACTION_SUBMITTED_ZH) {
    return t('ws.chat.event.satisfactionSubmitted', safeLocale)
  }
  return content
}

export function resolveWorkspaceSystemEventContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: string,
): string {
  return (
    resolveWorkspaceSessionTransferContent(content, metadata, locale)
    ?? sanitizeWorkspaceAgentEventContent(content, locale)
  )
}

export function resolveVisitorSystemEventContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: string,
): string {
  const safeLocale = normalizeLocale(locale)
  const eventType = typeof metadata?.event_type === 'string' ? metadata.event_type : ''
  const eventKey = eventType === 'open_agent_handoff_failed'
    ? 'chat.handoff.unavailableKeepChatting'
    : VISITOR_SYSTEM_EVENT_KEYS[eventType]
  const legacyKey = VISITOR_LEGACY_SYSTEM_CONTENT_KEYS[content.trim()]
  const satisfactionInviteKey = SATISFACTION_INVITE_ZH.test(content.trim())
    ? 'ws.chat.event.satisfactionInvited'
    : null

  return (
    resolveVisitorSessionTransferContent(content, metadata, locale)
    ?? resolveVisitorCollaboratorJoinedContent(content, metadata, locale)
    ?? (eventKey ? t(eventKey, safeLocale) : null)
    ?? (legacyKey ? t(legacyKey, safeLocale) : null)
    ?? (satisfactionInviteKey ? t(satisfactionInviteKey, safeLocale) : null)
    ?? content
  )
}

export function getWorkspaceHumanAgentLabel(locale: string): string {
  return t('ws.chat.queueAgent', normalizeLocale(locale))
}

export function getWorkspaceAgentAvatarLetter(isBot: boolean, agentName?: string | null): string {
  if (isBot) {
    return singleAvatarLetter(agentName || '智')
  }
  return singleAvatarLetter(agentName || '客')
}
