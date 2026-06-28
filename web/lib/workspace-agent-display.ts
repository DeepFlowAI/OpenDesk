import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import { singleAvatarLetter } from '@/lib/avatar-fallback'

const SATISFACTION_INVITE_ZH = /^.+发送了满意度邀请$/
export const SESSION_TRANSFER_EVENT_TYPE = 'session_transfer'
export const COLLABORATOR_JOINED_EVENT_TYPE = 'collaborator_joined'

function normalizeLocale(locale: string): Locale {
  return locale === 'en' ? 'en' : 'zh'
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
  return (
    resolveVisitorSessionTransferContent(content, metadata, locale)
    ?? resolveVisitorCollaboratorJoinedContent(content, metadata, locale)
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
