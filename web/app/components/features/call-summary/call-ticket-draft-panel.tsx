'use client'

import { useEffect, useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { CallRecordListItem } from '@/models/call-center'
import type { CallSummaryUsageResponse } from '@/models/call-summary'
import type { Ticket } from '@/models/ticket'
import { useCallSummaryUsage } from '@/service/use-call-summary'
import { TicketCreateForm } from '@/app/workspace/tickets/ticket-form-modal'

type Props = {
  callRecord: Pick<CallRecordListItem, 'id' | 'call_id' | 'user_id'>
  onClose: () => void
  onNotice?: (type: 'success' | 'error', text: string, payload?: { ticket?: Ticket }) => void
}

type StoredDraft = {
  call_record_id: number
  call_record_call_id?: string
  values: Record<string, unknown>
  initialized_from_summary_at: string | null
  updated_at: string
}

type DraftState = {
  callRecordId: number
  values: Record<string, unknown>
  initializedAt: string | null
}

function draftStorageKey(callRecordId: number): string {
  return `workspace_call_ticket_draft:${callRecordId}`
}

function readDraft(callRecord: Pick<CallRecordListItem, 'id' | 'call_id'>): StoredDraft | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(callRecord.id))
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredDraft
    if (parsed.call_record_id !== callRecord.id) return null
    if (parsed.call_record_call_id && parsed.call_record_call_id !== callRecord.call_id) return null

    const valueCallRecordId = parsed.values?.call_record_id
    if (valueCallRecordId != null && Number(valueCallRecordId) !== callRecord.id) return null

    return {
      ...parsed,
      call_record_call_id: parsed.call_record_call_id ?? callRecord.call_id,
      values: {
        ...parsed.values,
        call_record_id: callRecord.id,
      },
    }
  } catch {
    return null
  }
}

function writeDraft(
  callRecord: Pick<CallRecordListItem, 'id' | 'call_id'>,
  values: Record<string, unknown>,
  initializedAt: string | null,
): void {
  try {
    const scopedValues = {
      ...values,
      call_record_id: callRecord.id,
    }
    const draft: StoredDraft = {
      call_record_id: callRecord.id,
      call_record_call_id: callRecord.call_id,
      values: scopedValues,
      initialized_from_summary_at: initializedAt,
      updated_at: new Date().toISOString(),
    }
    window.localStorage.setItem(draftStorageKey(callRecord.id), JSON.stringify(draft))
  } catch {
    // localStorage can be unavailable in private browsing.
  }
}

function clearDraft(callRecordId: number): void {
  try {
    window.localStorage.removeItem(draftStorageKey(callRecordId))
  } catch {
    // localStorage can be unavailable in private browsing.
  }
}

function buildInitialValues(
  callRecord: Pick<CallRecordListItem, 'id' | 'user_id'>,
  summaryData: CallSummaryUsageResponse | undefined,
): {
  values: Record<string, unknown>
  initializedAt: string | null
} {
  const values: Record<string, unknown> = {
    status: 'open',
    priority: 'medium',
    call_record_id: callRecord.id,
  }
  if (callRecord.user_id) {
    values.user_id = callRecord.user_id
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

export function CallTicketDraftPanel({ callRecord, onClose, onNotice }: Props) {
  const { locale } = useLocaleStore()
  const summaryQuery = useCallSummaryUsage(callRecord.id)
  const [draftState, setDraftState] = useState<DraftState | null>(null)
  const [saveError, setSaveError] = useState(false)

  useEffect(() => {
    setSaveError(false)
  }, [callRecord.id])

  useEffect(() => {
    if (summaryQuery.isLoading) return

    const stored = readDraft(callRecord)
    if (stored) {
      setDraftState({
        callRecordId: callRecord.id,
        values: stored.values,
        initializedAt: stored.initialized_from_summary_at,
      })
      return
    }

    const built = buildInitialValues(callRecord, summaryQuery.data)
    setDraftState({
      callRecordId: callRecord.id,
      values: built.values,
      initializedAt: built.initializedAt,
    })
    writeDraft(callRecord, built.values, built.initializedAt)
  }, [callRecord.id, callRecord.call_id, callRecord.user_id, summaryQuery.data, summaryQuery.isLoading])

  const activeDraft = draftState?.callRecordId === callRecord.id ? draftState : null

  const resetKey = useMemo(
    () => `${callRecord.id}:${activeDraft ? JSON.stringify(activeDraft.values) : 'loading'}`,
    [callRecord.id, activeDraft],
  )

  const handleCancel = () => {
    const confirmed = window.confirm(t('ws.chatTicket.discardConfirm', locale))
    if (!confirmed) return
    clearDraft(callRecord.id)
    onClose()
  }

  if (!activeDraft) {
    return (
      <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
        <p className="text-xs text-muted-foreground">{t('ws.chatTicket.loading', locale)}</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-full flex-col">
      {summaryQuery.isError && (
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
        initialValues={activeDraft.values}
        columnsPerRowOverride={1}
        labelPositionOverride="top"
        bodyClassName="pb-20"
        footerClassName="sticky -bottom-5 z-20 -mx-5 -mb-5 mt-auto flex justify-end gap-2 border-t border-border bg-white px-5 py-3"
        submitLabel={t('ws.chatTicket.save', locale)}
        submittingLabel={t('ws.chatTicket.saving', locale)}
        cancelLabel={t('ws.chatTicket.cancel', locale)}
        onValuesChange={(values) => {
          if (draftState?.callRecordId !== callRecord.id) return
          setSaveError(false)
          writeDraft(callRecord, values, draftState.initializedAt)
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
          clearDraft(callRecord.id)
          onNotice?.('success', text, { ticket })
          onClose()
        }}
      />
    </div>
  )
}
