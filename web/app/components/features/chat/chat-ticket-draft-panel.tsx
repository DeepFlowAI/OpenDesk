'use client'

import { useEffect, useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Conversation } from '@/models/conversation'
import type { Ticket } from '@/models/ticket'
import { useSessionSummaryUsage } from '@/service/use-session-summary'
import { TicketCreateForm } from '@/app/workspace/tickets/ticket-form-modal'

type Props = {
  conversation: Conversation
  summaryEnabled?: boolean
  onClose: () => void
  onNotice?: (type: 'success' | 'error', text: string, payload?: { ticket?: Ticket }) => void
}

type StoredDraft = {
  conversation_id: number
  values: Record<string, unknown>
  initialized_from_summary_at: string | null
  updated_at: string
}

function draftStorageKey(conversationId: number): string {
  return `workspace_chat_ticket_draft:${conversationId}`
}

function readDraft(conversationId: number): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(conversationId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredDraft
    return parsed.conversation_id === conversationId ? parsed : null
  } catch {
    return null
  }
}

function writeDraft(conversationId: number, values: Record<string, unknown>, initializedAt: string | null): void {
  try {
    const draft: StoredDraft = {
      conversation_id: conversationId,
      values,
      initialized_from_summary_at: initializedAt,
      updated_at: new Date().toISOString(),
    }
    window.localStorage.setItem(draftStorageKey(conversationId), JSON.stringify(draft))
  } catch {
    // localStorage can be unavailable in private browsing.
  }
}

function clearDraft(conversationId: number): void {
  try {
    window.localStorage.removeItem(draftStorageKey(conversationId))
  } catch {
    // localStorage can be unavailable in private browsing.
  }
}

export function hasTicketDraft(conversationId: number): boolean {
  if (typeof window === 'undefined') return false
  return readDraft(conversationId) != null
}

function buildInitialValues(conversation: Conversation, summaryData: ReturnType<typeof useSessionSummaryUsage>['data']): {
  values: Record<string, unknown>
  initializedAt: string | null
} {
  const values: Record<string, unknown> = {
    status: 'open',
    priority: 'medium',
    conversation_id: conversation.id,
  }
  if (conversation.visitor?.id) {
    values.user_id = conversation.visitor.id
  }

  for (const field of summaryData?.fields ?? []) {
    const definition = field.field_definition
    if (!definition?.applicable_modules?.includes('ticket')) continue
    if (field.field_definition_id == null) continue
    const key = String(field.field_definition_id)
    const value = summaryData?.values?.[key]
    if (value === null || value === undefined || value === '') continue
    values[key] = value
  }

  return {
    values,
    initializedAt: summaryData ? new Date().toISOString() : null,
  }
}

export function ChatTicketDraftPanel({ conversation, summaryEnabled = true, onClose, onNotice }: Props) {
  const { locale } = useLocaleStore()
  const summaryQuery = useSessionSummaryUsage(conversation.id, { enabled: summaryEnabled })
  const [initialValues, setInitialValues] = useState<Record<string, unknown> | null>(null)
  const [initializedAt, setInitializedAt] = useState<string | null>(null)
  const [saveError, setSaveError] = useState(false)

  useEffect(() => {
    if (summaryEnabled && summaryQuery.isLoading) return

    const stored = readDraft(conversation.id)
    if (stored) {
      setInitialValues(stored.values)
      setInitializedAt(stored.initialized_from_summary_at)
      return
    }

    const built = buildInitialValues(conversation, summaryEnabled ? summaryQuery.data : undefined)
    setInitialValues(built.values)
    setInitializedAt(built.initializedAt)
    writeDraft(conversation.id, built.values, built.initializedAt)
  }, [conversation, summaryEnabled, summaryQuery.data, summaryQuery.isLoading])

  const resetKey = useMemo(
    () => `${conversation.id}:${initialValues ? JSON.stringify(initialValues) : 'loading'}`,
    [conversation.id, initialValues],
  )

  const handleCancel = () => {
    const confirmed = window.confirm(t('ws.chatTicket.discardConfirm', locale))
    if (!confirmed) return
    clearDraft(conversation.id)
    onClose()
  }

  if (!initialValues) {
    return (
      <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
        <p className="text-xs text-muted-foreground">{t('ws.chatTicket.loading', locale)}</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-full flex-col">
      {summaryEnabled && summaryQuery.isError && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-muted-foreground">
          {t('ws.chatTicket.summaryLoadFailed', locale)}
        </div>
      )}
      {saveError && (
        <div className="mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {t('ws.chatTicket.createFailed', locale)}
        </div>
      )}
      <TicketCreateForm
        resetKey={resetKey}
        initialValues={initialValues}
        columnsPerRowOverride={1}
        labelPositionOverride="top"
        bodyClassName="pb-20"
        footerClassName="sticky -bottom-5 z-20 -mx-5 -mb-5 mt-auto flex justify-end gap-2 border-t border-border bg-[#F5F5F5] px-5 pb-8 pt-3"
        submitLabel={t('ws.chatTicket.save', locale)}
        submittingLabel={t('ws.chatTicket.saving', locale)}
        cancelLabel={t('ws.chatTicket.cancel', locale)}
        onValuesChange={(values) => {
          setSaveError(false)
          writeDraft(conversation.id, values, initializedAt)
        }}
        onCancel={handleCancel}
        onError={() => {
          const text = t('ws.chatTicket.createFailed', locale)
          setSaveError(true)
          onNotice?.('error', text)
        }}
        onSuccess={(ticket) => {
          const ticketNumber = ticket.ticket_number || `#${ticket.id}`
          const text = `${t('ws.chatTicket.createSucceeded', locale)}${locale === 'zh' ? '：' : ': '}${ticketNumber}`
          clearDraft(conversation.id)
          onNotice?.('success', text, { ticket })
          onClose()
        }}
      />
    </div>
  )
}
