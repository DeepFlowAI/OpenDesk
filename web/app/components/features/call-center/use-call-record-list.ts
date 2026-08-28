'use client'

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import type { WorkspaceColumnConfigItem } from '@/components/workspace/columns-drawer'
import {
  downloadCallRecordsExport,
  type CallRecordsParams,
  useCallRecordFilterOptions,
  useCallRecords,
} from '@/service/use-call-center'
import { getDataScope, hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'

import { CALL_RECORD_COLUMN_DEFS } from './call-record-column-defs'

export type CallRecordFilterDraft = {
  startDate: string
  endDate: string
  direction: string
  keyword: string
  lastServingAgentId: string
  callSource: string
  lifecycleStatus: string
  finalizationStatus: string
  receptionType: string
  callResult: string
  hangupParty: string
  hangupReason: string
  initiatorAgentId: string
  queueValue: string
  userId: number | null
  recordingStatus: string
  minTotalDuration: string
  maxTotalDuration: string
  minRingDuration: string
  maxRingDuration: string
  minWaitDuration: string
  maxWaitDuration: string
  minTalkDuration: string
  maxTalkDuration: string
  satisfactionResults: string[]
  satisfactionSources: string[]
}

function dateInputValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function defaultDraft(): CallRecordFilterDraft {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - 6)
  return {
    startDate: dateInputValue(start), endDate: dateInputValue(end), direction: '', keyword: '',
    lastServingAgentId: '', callSource: '', lifecycleStatus: '', finalizationStatus: '',
    receptionType: '', callResult: '', hangupParty: '', hangupReason: '', initiatorAgentId: '',
    queueValue: '', userId: null, recordingStatus: '', minTotalDuration: '', maxTotalDuration: '',
    minRingDuration: '', maxRingDuration: '', minWaitDuration: '', maxWaitDuration: '',
    minTalkDuration: '', maxTalkDuration: '', satisfactionResults: [], satisfactionSources: [],
  }
}

function dayIso(value: string, endOfDay = false): string | undefined {
  if (!value) return undefined
  return new Date(`${value}T${endOfDay ? '23:59:59.999' : '00:00:00'}`).toISOString()
}

function durationMs(value: string): number | undefined {
  if (!value.trim()) return undefined
  return Number(value) * 1000
}

function buildParams(draft: CallRecordFilterDraft, page: number, perPage: number): CallRecordsParams {
  const [lastQueueType, lastQueueId] = draft.queueValue.split(':')
  return {
    page, per_page: perPage, direction: draft.direction || undefined,
    keyword: draft.keyword.trim() || undefined,
    start_time: dayIso(draft.startDate), end_time: dayIso(draft.endDate, true),
    last_serving_agent_id: draft.lastServingAgentId ? Number(draft.lastServingAgentId) : undefined,
    call_source: draft.callSource || undefined, lifecycle_status: draft.lifecycleStatus || undefined,
    finalization_status: draft.finalizationStatus || undefined,
    actual_reception_type: draft.receptionType || undefined, call_result: draft.callResult || undefined,
    hangup_party: draft.hangupParty || undefined, hangup_reason_code: draft.hangupReason || undefined,
    initiator_agent_id: draft.initiatorAgentId ? Number(draft.initiatorAgentId) : undefined,
    last_queue_type: lastQueueType || undefined, last_queue_id: lastQueueId ? Number(lastQueueId) : undefined,
    user_id: draft.userId ?? undefined, recording_status: draft.recordingStatus || undefined,
    min_total_duration_ms: durationMs(draft.minTotalDuration),
    max_total_duration_ms: durationMs(draft.maxTotalDuration),
    min_customer_ring_duration_ms: durationMs(draft.minRingDuration),
    max_customer_ring_duration_ms: durationMs(draft.maxRingDuration),
    min_agent_wait_duration_ms: durationMs(draft.minWaitDuration),
    max_agent_wait_duration_ms: durationMs(draft.maxWaitDuration),
    min_customer_agent_talk_duration_ms: durationMs(draft.minTalkDuration),
    max_customer_agent_talk_duration_ms: durationMs(draft.maxTalkDuration),
    satisfaction_result: draft.satisfactionResults.length ? draft.satisfactionResults : undefined,
    satisfaction_trigger_source: draft.satisfactionSources.length ? draft.satisfactionSources : undefined,
  }
}

function validateDraft(draft: CallRecordFilterDraft, locale: Locale): string | null {
  if (!draft.startDate || !draft.endDate) {
    return t('ws.records.calls.filter.error.dateRequired', locale)
  }
  const start = new Date(`${draft.startDate}T00:00:00`)
  const end = new Date(`${draft.endDate}T00:00:00`)
  if (start > end) return t('ws.records.calls.filter.error.dateOrder', locale)
  if ((end.getTime() - start.getTime()) / 86_400_000 > 89) {
    return t('ws.records.calls.filter.error.dateRange', locale)
  }
  const ranges = [
    [draft.minTotalDuration, draft.maxTotalDuration], [draft.minRingDuration, draft.maxRingDuration],
    [draft.minWaitDuration, draft.maxWaitDuration], [draft.minTalkDuration, draft.maxTalkDuration],
  ]
  for (const [minimum, maximum] of ranges) {
    const min = minimum === '' ? null : Number(minimum)
    const max = maximum === '' ? null : Number(maximum)
    if ((min != null && (!Number.isFinite(min) || min < 0 || min > 86400))
      || (max != null && (!Number.isFinite(max) || max < 0 || max > 86400))
      || (min != null && max != null && min > max)) {
      return t('ws.records.calls.filter.error.duration', locale)
    }
  }
  return null
}

function defaultColumns(): WorkspaceColumnConfigItem[] {
  return CALL_RECORD_COLUMN_DEFS.map((column, index) => ({
    field_id: null, field_key: column.key, visible: column.defaultVisible, sort_order: index,
  }))
}

function reconcileColumns(saved: WorkspaceColumnConfigItem[] | null): WorkspaceColumnConfigItem[] {
  if (!saved) return defaultColumns()
  const definitions = new Map(CALL_RECORD_COLUMN_DEFS.map((column) => [column.key, column]))
  const retained = saved
    .filter((column) => column.field_key && definitions.has(column.field_key))
    .sort((a, b) => a.sort_order - b.sort_order)
  const existing = new Set(retained.map((column) => column.field_key))
  for (const definition of CALL_RECORD_COLUMN_DEFS) {
    if (!existing.has(definition.key)) retained.push({
      field_id: null, field_key: definition.key, visible: false, sort_order: retained.length,
    })
  }
  const customer = retained.find((column) => column.field_key === 'customer_number')
  const others = retained.filter((column) => column.field_key !== 'customer_number')
  return [customer ? { ...customer, visible: true } : defaultColumns()[0], ...others]
    .map((column, index) => ({ ...column, sort_order: index }))
}

export function useCallRecordList() {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const [draft, setDraft] = useState<CallRecordFilterDraft>(() => defaultDraft())
  const [applied, setApplied] = useState<CallRecordFilterDraft>(() => defaultDraft())
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [exporting, setExporting] = useState(false)
  const [columnsOpen, setColumnsOpen] = useState(false)
  const [hasColumnOverride, setHasColumnOverride] = useState(false)
  const storageKey = user ? `ws_call_record_columns_${user.tenant_id}_${user.id}` : null
  const [columnConfig, setColumnConfig] = useState<WorkspaceColumnConfigItem[]>(defaultColumns)

  useEffect(() => {
    if (!storageKey) return
    try {
      const raw = window.localStorage.getItem(storageKey)
      setColumnConfig(reconcileColumns(raw ? JSON.parse(raw) : null))
      setHasColumnOverride(Boolean(raw))
    } catch {
      setColumnConfig(defaultColumns())
      setHasColumnOverride(false)
    }
  }, [storageKey])

  const canFilterByOwnership = getDataScope(user, 'call_record') !== 'self'
  const filterOptions = useCallRecordFilterOptions(canFilterByOwnership)
  const params = useMemo(() => buildParams(applied, page, perPage), [applied, page, perPage])
  const records = useCallRecords(params, { refetchInterval: 15_000 })

  useEffect(() => {
    const pages = records.data?.pages ?? 0
    if (pages > 0 && page > pages) setPage(pages)
  }, [page, records.data?.pages])

  const apply = () => {
    const error = validateDraft(draft, locale)
    if (error) return toast.error(error)
    setApplied({ ...draft, keyword: draft.keyword.trim() })
    setPage(1)
  }

  const reset = () => {
    const next = defaultDraft()
    setDraft(next)
    setApplied(next)
    setPage(1)
  }

  const saveColumns = (columns: WorkspaceColumnConfigItem[]) => {
    const reconciled = reconcileColumns(columns)
    setColumnConfig(reconciled)
    setHasColumnOverride(true)
    if (!storageKey) return
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(reconciled))
    } catch {
      toast.error(t('ws.records.calls.columnSaveFailed', locale))
    }
  }

  const resetColumns = () => {
    setColumnConfig(defaultColumns())
    setHasColumnOverride(false)
    if (!storageKey) return
    try { window.localStorage.removeItem(storageKey) } catch {
      toast.error(t('ws.records.calls.columnSaveFailed', locale))
    }
  }

  const exportRecords = async () => {
    setExporting(true)
    try {
      const { blob, filename } = await downloadCallRecordsExport(params)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
      toast.success(t('ws.records.calls.exportStarted', locale))
    } catch {
      toast.error(t('ws.records.calls.exportFailed', locale))
    } finally {
      setExporting(false)
    }
  }

  const visibleColumns = columnConfig
    .filter((column) => column.visible)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((column) => CALL_RECORD_COLUMN_DEFS.find((definition) => definition.key === column.field_key))
    .filter((column): column is NonNullable<typeof column> => Boolean(column))
  const moreFilterCount = [
    applied.callSource, applied.lifecycleStatus, applied.finalizationStatus, applied.receptionType,
    applied.callResult, applied.hangupParty, applied.hangupReason, applied.initiatorAgentId,
    applied.queueValue, applied.userId, applied.recordingStatus,
    Boolean(applied.minTotalDuration || applied.maxTotalDuration),
    Boolean(applied.minRingDuration || applied.maxRingDuration),
    Boolean(applied.minWaitDuration || applied.maxWaitDuration),
    Boolean(applied.minTalkDuration || applied.maxTalkDuration),
    Boolean(applied.satisfactionResults.length), Boolean(applied.satisfactionSources.length),
  ].filter(Boolean).length
  const defaults = defaultDraft()
  const hasActiveFilters = moreFilterCount > 0
    || Boolean(applied.keyword || applied.direction || applied.lastServingAgentId)
    || applied.startDate !== defaults.startDate
    || applied.endDate !== defaults.endDate

  return {
    locale, draft, setDraft, applied, apply, reset, page, setPage, perPage, setPerPage,
    params, records, exporting, exportRecords, canExport: hasPermission(user, 'call.record.export'),
    canFilterByOwnership, filterOptions: filterOptions.data, moreFilterCount,
    hasActiveFilters, columnsOpen, setColumnsOpen, hasColumnOverride,
    columnConfig, saveColumns, resetColumns, visibleColumns,
    columnFields: CALL_RECORD_COLUMN_DEFS.map((column) => ({
      id: null, key: column.key, name: t(column.labelKey, locale),
    })),
  }
}
