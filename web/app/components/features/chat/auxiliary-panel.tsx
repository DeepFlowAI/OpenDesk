'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/navigation'
import { IconBan, IconCheck, IconCircleCheck, IconCopy, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import type { Conversation } from '@/models/conversation'
import type { ConversationUserStatisticItem } from '@/models/conversation-user-statistics'
import type { Ticket } from '@/models/ticket'
import type { UnifiedField } from '@/models/field-definition'
import type { CustomFieldValue, UpdateUserPayload, User } from '@/models/user'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useConversationUserStatistics } from '@/service/use-conversation-user-statistics'
import { useUpdateUser, useUser } from '@/service/use-users'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { SessionSummaryFields } from '@/app/components/features/session-summary/session-summary-fields'
import { ChatTicketDraftPanel, hasTicketDraft } from '@/app/components/features/chat/chat-ticket-draft-panel'
import { KnowledgeAssistant, type KnowledgeAssistantActionContext } from '@/app/components/features/knowledge/knowledge-assistant'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { FieldType } from '@/types/field-enums'
import { getLinkedSelectTypeConfig } from '@/lib/field-linked-select-config'

type AuxiliaryTab = 'basic' | 'summary' | 'ticket' | 'knowledge'

type Props = {
  conversation: Conversation | null
  connected: boolean
  width: number
  ticketDraftOpen?: boolean
  onCloseTicketDraft?: (conversationId: number) => void
  onKnowledgeUse?: (messageText: string) => void
  onKnowledgeSend?: (messageText: string) => void | Promise<void>
}

const SYSTEM_KEY_ALIAS: Record<string, keyof User> = {
  nickname: 'name',
  assignee: 'agent_id',
  assignee_group: 'assignee_group_id',
}
const EDITABLE_SYSTEM_KEYS = new Set([
  'name',
  'email',
  'phone',
  'gender',
  'level',
  'address',
  'remark',
  'web_id',
  'blacklist',
  'organization_id',
  'agent_id',
  'assignee_group_id',
])
const READONLY_FIELD_KEYS = new Set(['id', 'public_id', 'external_id', 'created_at', 'updated_at', 'channel_id'])
const INSTANT_SAVE_FIELD_TYPES = new Set<FieldType>([
  FieldType.SINGLE_SELECT,
  FieldType.SINGLE_SELECT_TREE,
  FieldType.FILE,
  FieldType.ORGANIZATION_SELECT,
  FieldType.EMPLOYEE_SELECT,
  FieldType.GROUP_SELECT,
])

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

export function AuxiliaryPanel({
  conversation,
  connected,
  width,
  ticketDraftOpen = false,
  onCloseTicketDraft,
  onKnowledgeUse,
  onKnowledgeSend,
}: Props) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<AuxiliaryTab>('basic')
  const [summaryDirty, setSummaryDirty] = useState(false)
  const [blacklistConfirmOpen, setBlacklistConfirmOpen] = useState(false)
  const [ticketNotice, setTicketNotice] = useState<{ type: 'success' | 'error'; text: string; ticket?: Ticket } | null>(null)
  const visitorId = conversation?.visitor?.id ?? 0
  const visitorPublicId = conversation?.visitor?.public_id ?? ''
  const visitorDetailRef = visitorPublicId || (visitorId > 0 ? String(visitorId) : '')
  const conversationShareCode = conversation?.share_code || conversation?.public_id || ''
  const canViewUsers = hasPermission(currentUser, 'crm.workspace.user.view')
  const canEditUser = hasPermission(currentUser, 'crm.workspace.user.edit')
  const canCreateTicket = hasPermission(currentUser, 'ticket.workspace.create')
  const canViewKnowledge = hasPermission(currentUser, 'knowledge.workspace.view')
  const isPeerConversation = conversation?.viewer_relation === 'peer' || conversation?.viewer_relation === 'collaborator'
  const showSummaryTab = !!conversation && !isPeerConversation
  const showTicketTab = !!conversation && canCreateTicket && (ticketDraftOpen || hasTicketDraft(conversation.id))
  const conversationClosed = conversation?.status === 'closed'
  const isWebChannel = conversation?.channel?.channel_type?.toLowerCase() === 'web'
  const knowledgeUseReason = !conversation
    ? t('ws.knowledge.selectConversation', locale)
    : conversationClosed
      ? t('ws.knowledge.conversationEnded', locale)
      : undefined
  const knowledgeSendReason = knowledgeUseReason ?? (!connected ? t('ws.knowledge.disconnected', locale) : undefined)
  const visibleActiveTab =
    (activeTab === 'summary' && !showSummaryTab) || (activeTab === 'ticket' && !showTicketTab)
      ? 'basic'
      : activeTab

  const userQuery = useUser(visitorId)
  const fieldsQuery = useUnifiedFields({ domain: 'user', locale, include_metadata: true })
  const userStatsQuery = useConversationUserStatistics(conversation?.id ?? 0, {
    enabled: Boolean(conversation && visibleActiveTab === 'basic' && visitorId > 0),
  })
  const updateUser = useUpdateUser()
  const prevConversationIdRef = useRef<number | null>(null)

  useEffect(() => {
    if (ticketDraftOpen && showTicketTab) {
      setActiveTab('ticket')
    }
  }, [ticketDraftOpen, showTicketTab])

  useEffect(() => {
    const currentId = conversation?.id ?? null
    if (currentId === prevConversationIdRef.current) return
    prevConversationIdRef.current = currentId

    if (currentId == null) return
    if (ticketDraftOpen && showTicketTab) return

    setActiveTab('basic')
  }, [conversation?.id, ticketDraftOpen, showTicketTab])

  useEffect(() => {
    if (activeTab === 'ticket' && !showTicketTab) {
      setActiveTab(conversation ? 'basic' : canViewKnowledge ? 'knowledge' : 'basic')
    }
    if (activeTab === 'summary' && !showSummaryTab) {
      setActiveTab(conversation ? 'basic' : canViewKnowledge ? 'knowledge' : 'basic')
    }
    if ((activeTab === 'basic' || activeTab === 'summary') && !conversation && canViewKnowledge) {
      setActiveTab('knowledge')
    }
    if (activeTab === 'knowledge' && !canViewKnowledge) {
      setActiveTab(conversation ? 'basic' : 'basic')
    }
  }, [activeTab, canViewKnowledge, conversation, showSummaryTab, showTicketTab])

  useEffect(() => {
    if (!ticketNotice) return
    const timer = window.setTimeout(() => setTicketNotice(null), 3000)
    return () => window.clearTimeout(timer)
  }, [ticketNotice])

  const workspaceFields = useMemo(
    () =>
      (fieldsQuery.data?.items ?? [])
        .filter((field) => field.source !== 'metadata' && field.status === 'active' && field.show_in_workspace === true)
        .sort((a, b) => a.sort_order - b.sort_order),
    [fieldsQuery.data?.items],
  )

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field)
      setTimeout(() => setCopiedField(null), 2000)
    })
  }

  const switchTab = (nextTab: AuxiliaryTab) => {
    if (activeTab === 'summary' && nextTab !== 'summary' && summaryDirty) {
      const confirmed = window.confirm(t('ws.summary.unsavedConfirm', locale))
      if (!confirmed) return
    }
    setActiveTab(nextTab)
  }

  const noticeTicketHref = ticketNotice?.type === 'success' && ticketNotice.ticket
    ? `/workspace/tickets/${ticketNotice.ticket.id}?from=list`
    : null

  const handleKnowledgeUse = (context: KnowledgeAssistantActionContext) => {
    onKnowledgeUse?.(context.messageText)
  }

  const handleKnowledgeSend = async (context: KnowledgeAssistantActionContext) => {
    await onKnowledgeSend?.(context.messageText)
  }

  const handleToggleBlacklist = () => {
    if (!userQuery.data || visitorId <= 0 || updateUser.isPending) return
    setBlacklistConfirmOpen(true)
  }

  const handleConfirmBlacklist = async () => {
    const user = userQuery.data
    if (!user || visitorId <= 0 || updateUser.isPending) return
    const isBlocked = user.blacklist === 'blocked'
    try {
      await updateUser.mutateAsync({
        id: visitorId,
        data: { blacklist: isBlocked ? null : 'blocked' },
      })
      setBlacklistConfirmOpen(false)
      setTicketNotice({
        type: 'success',
        text: isBlocked ? t('ws.chat.unblockUserSuccess', locale) : t('ws.chat.blockUserSuccess', locale),
      })
    } catch {
      setBlacklistConfirmOpen(false)
      setTicketNotice({
        type: 'error',
        text: isBlocked ? t('ws.chat.unblockUserFailed', locale) : t('ws.chat.blockUserFailed', locale),
      })
    }
  }

  return (
    <div className="relative flex shrink-0 flex-col bg-[#F5F5F5]" style={{ width }}>
      {ticketNotice && (
        <div
          className={cn(
            'absolute left-5 right-5 top-4 z-20 rounded-md border px-3 py-2 text-left text-xs shadow-sm transition-colors',
            ticketNotice.type === 'success'
              ? 'border-green-200 bg-green-50 text-green-700'
              : 'border-destructive/30 bg-destructive/10 text-destructive',
            noticeTicketHref ? 'cursor-pointer hover:bg-green-100' : 'cursor-default',
          )}
          role="status"
          aria-live="polite"
        >
          {noticeTicketHref ? (
            <button
              type="button"
              onClick={() => {
                setTicketNotice(null)
                router.push(noticeTicketHref)
              }}
              className="block w-full cursor-pointer text-left"
            >
              {ticketNotice.text}
            </button>
          ) : (
            ticketNotice.text
          )}
        </div>
      )}
      {conversation || canViewKnowledge ? (
        <>
          <div className="mx-5 mb-4 mt-5 flex rounded-lg border border-border bg-background p-0.5">
            {conversation && (
              <>
                <button
                  type="button"
                  onClick={() => switchTab('basic')}
                  className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', visibleActiveTab === 'basic' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                >
                  {t('ws.summary.tab.basic', locale)}
                </button>
                {showSummaryTab && (
                  <button
                    type="button"
                    onClick={() => switchTab('summary')}
                    className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', visibleActiveTab === 'summary' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
                  >
                    {t('ws.summary.tab.summary', locale)}
                  </button>
                )}
              </>
            )}
            {showTicketTab && (
              <button
                type="button"
                onClick={() => switchTab('ticket')}
                className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', visibleActiveTab === 'ticket' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              >
                {t('ws.chatTicket.tab', locale)}
              </button>
            )}
            {canViewKnowledge && (
              <button
                type="button"
                onClick={() => switchTab('knowledge')}
                className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', visibleActiveTab === 'knowledge' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
              >
                {t('ws.knowledge.title', locale)}
              </button>
            )}
          </div>
          <div className={cn('flex-1', visibleActiveTab === 'knowledge' ? 'flex min-h-0 flex-col overflow-hidden' : 'overflow-y-auto px-5 pb-5 pt-0')}>
            {visibleActiveTab === 'knowledge' ? (
              <KnowledgeAssistant
                mode="chat"
                conversationId={conversation?.id ?? null}
                canUse={Boolean(conversation && !conversationClosed)}
                useDisabledReason={knowledgeUseReason}
                canSend={Boolean(conversation && !conversationClosed && connected)}
                sendDisabledReason={knowledgeSendReason}
                showRecommendations
                onUse={handleKnowledgeUse}
                onSend={handleKnowledgeSend}
              />
            ) : conversation && visibleActiveTab === 'basic' ? (
              <>
                <section className="flex flex-col gap-[14px]">
                  <InfoRow label={t('ws.chat.startTime', locale)} value={formatDateTime(conversation.started_at || conversation.created_at)} />
                  <InfoRow
                    label={t('ws.chat.visitorId', locale)}
                    value={visitorPublicId || '-'}
                    copyable={!!visitorPublicId}
                    onCopy={(v) => handleCopy(v, 'visitorId')}
                    copied={copiedField === 'visitorId'}
                  />
                  <InfoRow
                    label={t('ws.chat.shareCode', locale)}
                    value={conversationShareCode}
                    copyable={!!conversationShareCode}
                    onCopy={(v) => handleCopy(v, 'shareCode')}
                    copied={copiedField === 'shareCode'}
                  />
                  <InfoRow label={t('ws.chat.sourceChannel', locale)} value={conversation.channel?.channel_type || 'Web'} />
                  <InfoRow label={t('ws.chat.channelName', locale)} value={conversation.channel?.name || '-'} />
                  <InfoRow label={t('ws.chat.agentGroup', locale)} value={conversation.group?.name || '-'} />
                  {isWebChannel && (
                    <>
                      <InfoRow label={t('ws.chat.visitorSystem', locale)} value={conversation.visitor_system || '-'} />
                      <InfoRow label={t('ws.chat.visitorBrowser', locale)} value={conversation.visitor_browser || '-'} />
                      <InfoRow label={t('ws.chat.visitorIp', locale)} value={conversation.visitor_ip || '-'} />
                    </>
                  )}
                </section>

                <section className="mt-5 border-t border-border pt-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <h3 className="shrink-0 text-sm font-semibold text-[#1a1a1a]">{t('ws.chat.userInfo', locale)}</h3>
                      {canEditUser && userQuery.data && visitorId > 0 && (
                        <button
                          type="button"
                          onClick={handleToggleBlacklist}
                          disabled={updateUser.isPending}
                          className={cn(
                            'inline-flex h-7 shrink-0 items-center gap-1 rounded-md border px-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                            'border-transparent bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground',
                          )}
                        >
                          {updateUser.isPending ? (
                            <IconLoader2 size={13} className="animate-spin" />
                          ) : userQuery.data.blacklist === 'blocked' ? (
                            <IconCircleCheck size={13} />
                          ) : (
                            <IconBan size={13} />
                          )}
                          <span>
                            {userQuery.data.blacklist === 'blocked'
                              ? t('ws.chat.unblockUser', locale)
                              : t('ws.chat.blockUser', locale)}
                          </span>
                        </button>
                      )}
                    </div>
                    {canViewUsers && visitorDetailRef && (
                      <button
                        type="button"
                        onClick={() => router.push(`/workspace/users/${visitorDetailRef}`)}
                        className="shrink-0 text-xs font-medium text-primary underline-offset-2 hover:underline"
                      >
                        {t('ws.chat.viewUser', locale)}
                      </button>
                    )}
                  </div>
                  <UserInfoSection
                    locale={locale}
                    visitorId={visitorId}
                    statistics={userStatsQuery.data?.items ?? []}
                    statisticsLoading={userStatsQuery.isLoading}
                    statisticsError={userStatsQuery.isError}
                    user={userQuery.data ?? null}
                    fields={workspaceFields}
                    isLoading={userQuery.isLoading || fieldsQuery.isLoading}
                    isError={userQuery.isError || fieldsQuery.isError}
                    isSaving={updateUser.isPending}
                    canEdit={canEditUser}
                    onRetry={() => {
                      void userQuery.refetch()
                      void fieldsQuery.refetch()
                    }}
                    onStatisticsRetry={() => {
                      void userStatsQuery.refetch()
                    }}
                    onSave={(field, value) => updateUser.mutateAsync({ id: visitorId, data: buildUpdatePayload(field, value) })}
                  />
                </section>
              </>
            ) : conversation && visibleActiveTab === 'summary' && showSummaryTab ? (
              <SessionSummaryFields conversationId={conversation.id} onDirtyChange={setSummaryDirty} />
            ) : conversation ? (
              <ChatTicketDraftPanel
                conversation={conversation}
                summaryEnabled={!isPeerConversation}
                onNotice={(type, text, payload) => setTicketNotice({ type, text, ticket: payload?.ticket })}
                onClose={() => {
                  onCloseTicketDraft?.(conversation.id)
                  setActiveTab('basic')
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center px-5">
                <p className="text-sm text-[#737373]">{t('ws.chat.selectHint', locale)}</p>
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center px-5">
          <p className="text-sm text-[#737373]">{t('ws.chat.selectHint', locale)}</p>
        </div>
      )}
      <ConfirmDialog
        open={blacklistConfirmOpen}
        title={userQuery.data?.blacklist === 'blocked' ? t('ws.chat.unblockUser', locale) : t('ws.chat.blockUser', locale)}
        message={userQuery.data?.blacklist === 'blocked' ? t('ws.chat.unblockUserConfirm', locale) : t('ws.chat.blockUserConfirm', locale)}
        confirmLabel={t('ws.common.confirm', locale)}
        cancelLabel={t('ws.common.cancel', locale)}
        loading={updateUser.isPending}
        onCancel={() => {
          if (!updateUser.isPending) setBlacklistConfirmOpen(false)
        }}
        onConfirm={handleConfirmBlacklist}
      />
    </div>
  )
}

function UserInfoSection({
  locale,
  visitorId,
  statistics,
  statisticsLoading,
  statisticsError,
  user,
  fields,
  isLoading,
  isError,
  isSaving,
  canEdit,
  onRetry,
  onStatisticsRetry,
  onSave,
}: {
  locale: Locale
  visitorId: number
  statistics: ConversationUserStatisticItem[]
  statisticsLoading: boolean
  statisticsError: boolean
  user: User | null
  fields: UnifiedField[]
  isLoading: boolean
  isError: boolean
  isSaving: boolean
  canEdit: boolean
  onRetry: () => void
  onStatisticsRetry: () => void
  onSave: (field: UnifiedField, value: unknown) => Promise<unknown>
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState<unknown>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const statisticsStrip = (
    <UserStatisticsStrip
      locale={locale}
      items={statistics}
      isLoading={statisticsLoading}
      isError={statisticsError}
      onRetry={onStatisticsRetry}
    />
  )

  if (!visitorId) {
    return <PanelStateMessage>{t('ws.chat.noLinkedUser', locale)}</PanelStateMessage>
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-[14px]">
        {statisticsStrip}
        <PanelStateMessage>{t('ws.chat.userInfoLoading', locale)}</PanelStateMessage>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-[14px]">
        {statisticsStrip}
        <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
          <p className="text-xs text-destructive">{t('ws.chat.userInfoLoadFailed', locale)}</p>
          <button type="button" onClick={onRetry} className="mt-2 text-xs font-medium text-primary hover:underline">
            {t('ws.chat.retry', locale)}
          </button>
        </div>
      </div>
    )
  }

  if (!user) {
    return <PanelStateMessage>{t('ws.chat.noLinkedUser', locale)}</PanelStateMessage>
  }

  if (fields.length === 0) {
    return (
      <div className="flex flex-col gap-[14px]">
        {statisticsStrip}
        <PanelStateMessage>{t('ws.chat.noWorkspaceFields', locale)}</PanelStateMessage>
      </div>
    )
  }

  const startEdit = (field: UnifiedField) => {
    if (!canEdit || !isFieldEditable(field)) return
    setEditingKey(getFieldIdentity(field))
    setDraftValue(getFieldRawValue(user, field))
    setFieldError(null)
  }

  const cancelEdit = () => {
    setEditingKey(null)
    setDraftValue(null)
    setFieldError(null)
  }

  const saveEdit = async (field: UnifiedField, submittedValue: unknown = draftValue) => {
    const originalValue = getFieldRawValue(user, field)
    if (areFieldValuesEqual(originalValue, submittedValue)) {
      cancelEdit()
      return
    }
    const validationError = validateFieldValue(field, submittedValue, locale)
    if (validationError) {
      setFieldError(validationError)
      return
    }
    try {
      await onSave(field, submittedValue)
      cancelEdit()
    } catch {
      setDraftValue(originalValue)
      setFieldError(t('ws.chat.saveFieldFailed', locale))
    }
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {statisticsStrip}
      {fields.map((field) => {
        const identity = getFieldIdentity(field)
        const editing = editingKey === identity
        const editable = canEdit && isFieldEditable(field)
        const resolveFieldValue = (targetField: UnifiedField) =>
          editingKey === getFieldIdentity(targetField) ? draftValue : getFieldRawValue(user, targetField)
        return (
          <EditableInfoRow
            key={identity}
            field={field}
            value={editing ? draftValue : getFieldRawValue(user, field)}
            typeConfig={getLinkedSelectTypeConfig(field, fields, resolveFieldValue)}
            editing={editing}
            editable={editable}
            saving={editing && isSaving}
            error={editing ? fieldError : null}
            locale={locale}
            onEdit={() => startEdit(field)}
            onChange={setDraftValue}
            onCancel={cancelEdit}
            onSave={() => saveEdit(field)}
            onSaveValue={(value) => saveEdit(field, value)}
          />
        )
      })}
      <div aria-hidden className="h-[200px] shrink-0" />
    </div>
  )
}

function UserStatisticsStrip({
  locale,
  items,
  isLoading,
  isError,
  onRetry,
}: {
  locale: Locale
  items: ConversationUserStatisticItem[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}) {
  if (isLoading) {
    return (
      <div className="flex h-[54px] items-center gap-3 rounded-md border border-border bg-background/70 px-3 py-2">
        <div className="h-8 flex-1 animate-pulse rounded bg-muted" />
        <div className="h-8 flex-1 animate-pulse rounded bg-muted" />
        <div className="h-8 flex-1 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-md border border-border bg-background/70 px-3 py-2 text-center">
        <p className="text-xs text-muted-foreground">{t('userStats.workspace.loadFailed', locale)}</p>
        <button type="button" onClick={onRetry} className="mt-1 text-xs font-medium text-primary hover:underline">
          {t('ws.chat.retry', locale)}
        </button>
      </div>
    )
  }

  if (items.length === 0) return null

  return (
    <div className="flex rounded-md border border-border bg-background/70 py-2">
      {items.map((item, index) => (
        <div
          key={item.key}
          className={cn(
            'flex min-w-0 flex-1 flex-col items-center justify-center gap-1 px-2 text-center',
            index > 0 && 'border-l border-border',
          )}
        >
          {item.key === 'tickets' ? (
            <div className="text-sm leading-5">
              <span className="text-destructive">{formatStatNumber(item.unresolved_value)}</span>
              <span className="text-foreground">/</span>
              <span className="text-foreground">{formatStatNumber(item.total_value)}</span>
            </div>
          ) : (
            <div className="text-sm leading-5 text-foreground">
              {formatStatNumber(item.value)}
            </div>
          )}
          <div className="truncate text-xs text-muted-foreground">{t(`userStats.workspace.${item.key}`, locale)}</div>
        </div>
      ))}
    </div>
  )
}

function formatStatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return String(value)
}

function EditableInfoRow({
  field,
  value,
  typeConfig,
  editing,
  editable,
  saving,
  error,
  locale,
  onEdit,
  onChange,
  onCancel,
  onSave,
  onSaveValue,
}: {
  field: UnifiedField
  value: unknown
  typeConfig: Record<string, unknown>
  editing: boolean
  editable: boolean
  saving: boolean
  error: string | null
  locale: Locale
  onEdit: () => void
  onChange: (value: unknown) => void
  onCancel: () => void
  onSave: () => void
  onSaveValue: (value: unknown) => void
}) {
  const shouldSaveOnChange = INSTANT_SAVE_FIELD_TYPES.has(field.field_type)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className="text-[12px] text-[#999999]">{field.name}</span>
        {field.help_text && <FieldHelpTooltip text={field.help_text} />}
      </div>

      {editing ? (
        <div
          onBlurCapture={(event) => {
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
            if (field.field_type === FieldType.FILE) return
            void onSave()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              onCancel()
            }
            if (event.key === 'Enter' && field.field_type !== FieldType.MULTI_LINE_TEXT && !INSTANT_SAVE_FIELD_TYPES.has(field.field_type)) {
              event.preventDefault()
              void onSave()
            }
          }}
        >
          <div className="relative">
            <UnifiedFieldValueEditor
              field={field}
              value={value}
              typeConfig={typeConfig}
              onChange={(nextValue) => {
                onChange(nextValue)
                if (shouldSaveOnChange) void onSaveValue(nextValue)
              }}
              disabled={saving}
              className="min-h-8 text-[13px]"
              autoFocus
            />
            {saving && <IconLoader2 size={14} className="absolute right-2 top-2.5 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
        </div>
      ) : (
        <button
          type="button"
          onClick={onEdit}
          disabled={!editable}
          className={cn(
            'min-h-5 max-w-full rounded-sm text-left text-[13px] text-[#1a1a1a] outline-none',
            editable && 'cursor-text hover:bg-black/[0.04] focus-visible:ring-2 focus-visible:ring-ring',
            !editable && 'cursor-default',
          )}
          aria-label={editable ? `${t('ws.chat.editField', locale)} ${field.name}` : field.name}
        >
          <FieldValueDisplay
            fieldType={field.field_type}
            value={value}
            typeConfig={field.type_config ?? {}}
            options={field.options}
            treeNodes={field.tree_nodes}
            className="break-words text-[13px]"
          />
        </button>
      )}
    </div>
  )
}

function FieldHelpTooltip({ text }: { text: string }) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)

  const showTooltip = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return

    const tooltipWidth = 176
    const viewportMargin = 8
    const left = Math.min(
      Math.max(rect.left + rect.width / 2 - tooltipWidth / 2, viewportMargin),
      window.innerWidth - tooltipWidth - viewportMargin,
    )

    setPosition({ left, top: rect.bottom + 6 })
    setOpen(true)
  }

  const hideTooltip = () => setOpen(false)

  return (
    <>
      <span
        ref={triggerRef}
        tabIndex={0}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-border text-[10px] text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        ?
      </span>
      {open &&
        position &&
        createPortal(
          <span
            className="pointer-events-none fixed z-[100] w-44 rounded-md border border-border bg-popover px-2 py-1.5 text-left text-xs text-popover-foreground shadow-md"
            style={{ left: position.left, top: position.top }}
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  )
}

function PanelStateMessage({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
      <p className="text-xs text-[#737373]">{children}</p>
    </div>
  )
}

function InfoRow({
  label,
  value,
  copyable,
  onCopy,
  copied,
}: {
  label: string
  value: string
  copyable?: boolean
  onCopy?: (v: string) => void
  copied?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[12px] text-[#999999]">{label}</span>
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="min-w-0 break-all text-[13px] text-[#1a1a1a]">{value}</span>
        {copyable && (
          <button
            type="button"
            onClick={() => onCopy?.(value)}
            className="flex h-5 w-5 items-center justify-center rounded text-[#999999] transition-colors hover:text-[#1a1a1a]"
          >
            {copied ? <IconCheck size={14} className="text-emerald-600" /> : <IconCopy size={14} />}
          </button>
        )}
      </div>
    </div>
  )
}

function getFieldIdentity(field: UnifiedField): string {
  return field.key ?? `custom:${field.id ?? field.name}`
}

function getSystemKey(field: UnifiedField): keyof User | null {
  if (field.source === 'custom') return null
  if (!field.key) return null
  return SYSTEM_KEY_ALIAS[field.key] ?? (field.key as keyof User)
}

function getFieldRawValue(user: User, field: UnifiedField): unknown {
  const systemKey = getSystemKey(field)
  if (systemKey) return user[systemKey]
  if (field.key) return user.custom_fields?.[field.key] ?? (field.id != null ? user.custom_fields?.[String(field.id)] : null)
  if (field.id != null) return user.custom_fields?.[String(field.id)] ?? null
  return null
}

function isFieldEditable(field: UnifiedField): boolean {
  if (field.source === 'custom') return field.id != null
  if (!field.key || READONLY_FIELD_KEYS.has(field.key)) return false
  const systemKey = getSystemKey(field)
  return !!systemKey && EDITABLE_SYSTEM_KEYS.has(systemKey)
}

function buildUpdatePayload(field: UnifiedField, value: unknown): UpdateUserPayload {
  const systemKey = getSystemKey(field)
  if (systemKey && EDITABLE_SYSTEM_KEYS.has(systemKey)) {
    return { [systemKey]: normalizeEmptyValue(value) } as UpdateUserPayload
  }
  const customKey = field.key ?? (field.id != null ? String(field.id) : null)
  if (customKey) {
    return { custom_fields: { [customKey]: normalizeEmptyValue(value) as CustomFieldValue } }
  }
  return {}
}

function normalizeEmptyValue(value: unknown): unknown {
  return value === '' ? null : value
}

function areFieldValuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(normalizeEmptyValue(a)) === JSON.stringify(normalizeEmptyValue(b))
}

function validateFieldValue(field: UnifiedField, value: unknown, locale: Locale): string | null {
  const required = (field.type_config?.required as boolean | undefined) === true
  const normalized = normalizeEmptyValue(value)
  if (required && (normalized === null || normalized === undefined)) {
    return t('ws.chat.fieldRequired', locale)
  }
  if (field.field_type === FieldType.EMAIL && typeof normalized === 'string' && normalized) {
    const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)
    if (!valid) return t('ws.chat.invalidFormat', locale)
  }
  return null
}
