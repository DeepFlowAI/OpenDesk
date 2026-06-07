'use client'

import { useState, useMemo, useCallback, useEffect, useRef, type ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconChevronDown,
  IconChevronRight,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { cn } from '@/lib/utils'
import {
  useTicket,
  useTicketChanges,
  useUpdateTicket,
  useFormLayoutByScene,
  useInteractionRules,
} from '@/service/use-tickets'
import { useUser } from '@/service/use-users'
import { useOrganization } from '@/service/use-organizations'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type {
  FdFormLayoutField,
  FdFormLayoutSection,
  FdFormLayoutTab,
} from '@/models/form-layout'
import type { FdInteractionRule, InteractionRuleCondition } from '@/models/interaction-rule'
import type { CustomFieldValue, TicketChange, TicketChangeEntry, TicketChangeValue } from '@/models/ticket'
import type { UnifiedField } from '@/models/field-definition'
import { FieldType } from '@/types/field-enums'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import {
  FieldValueDisplay,
  formatActorFieldValue,
} from '@/app/components/features/field-system/field-value-display'
import { ActivityActorAvatar } from '@/app/components/features/ticket/activity-actor-avatar'
import {
  ActivityTimeline,
  ActivityTimelineRow,
} from '@/app/components/features/ticket/activity-timeline-row'
import { TicketCommentThread } from '@/app/components/features/ticket/ticket-comment-thread'
import { richTextToPlainCell } from '@/lib/rich-text-plain'
import {
  coalescePillOptions,
  FieldOptionPill,
  type FieldSelectOption,
} from '@/app/components/features/field-system/field-select-pill-editors'
import { buildSelectLookup } from '@/lib/workspace-group'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'
import { useEmployee } from '@/service/use-employees'
import { useEmployeeGroup } from '@/service/use-employee-groups'
import { SessionDetailDrawer } from '@/app/components/features/session-records/session-detail-drawer'
import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import { hasPermission } from '@/utils/permissions'

type FieldState = 'hidden' | 'required' | 'optional' | 'readonly'
const TICKET_CHANGE_CREATE_FIELD_KEY = '__create__'
const TICKET_WORKFLOW_FIELD_SOURCE = 'ticket_workflow'

/** Maps layout field_source to UnifiedField.domain for scoped definition lookup. */
function unifiedDomainForLayoutFieldSource(source: FdFormLayoutField['field_source']): string {
  switch (source) {
    case 'user':
      return 'user'
    case 'organization':
      return 'organization'
    case 'ticket':
    case 'ticket_metadata':
    default:
      return 'ticket'
  }
}

function fieldAppliesToTicket(field: UnifiedField): boolean {
  return field.domain === 'ticket'
    || (field.domain === 'shared_pool' && (field.applicable_modules?.some((m) => m === 'ticket') ?? false))
}

function registerFieldLookup(map: Map<string, UnifiedField>, field: UnifiedField) {
  const domains = new Set<string>([field.domain])
  if (fieldAppliesToTicket(field)) domains.add('ticket')

  for (const domain of domains) {
    if (field.key) map.set(`${domain}:${field.key}`, field)
    if (field.id != null) map.set(`${domain}:${field.id}`, field)
  }
}

function addScopedCustomFieldValueAliases(
  target: Record<string, unknown>,
  valueScope: 'ticket' | 'user' | 'org',
  lookupDomain: 'ticket' | 'user' | 'organization',
  rawKey: string,
  value: unknown,
  fieldDefMap: Map<string, UnifiedField>,
) {
  target[`${valueScope}:${rawKey}`] = value
  const fieldDef = fieldDefMap.get(`${lookupDomain}:${rawKey}`)
  if (fieldDef?.source !== 'custom') return

  if (fieldDef.key) target[`${valueScope}:${fieldDef.key}`] = value
  if (fieldDef.id != null) target[`${valueScope}:${fieldDef.id}`] = value
}

function addTicketEditValueAliases(
  target: Record<string, unknown>,
  rawKey: string,
  value: unknown,
  fieldDefMap: Map<string, UnifiedField>,
) {
  target[rawKey] = value
  const fieldDef = fieldDefMap.get(`ticket:${rawKey}`)
  if (fieldDef?.source !== 'custom') return

  if (fieldDef.key) target[fieldDef.key] = value
  if (fieldDef.id != null) target[String(fieldDef.id)] = value
}

function ticketPayloadFieldKey(rawKey: string, fieldDefMap: Map<string, UnifiedField>): string {
  const fieldDef = fieldDefMap.get(`ticket:${rawKey}`)
  if (fieldDef?.source !== 'custom') return rawKey
  return fieldDef.key ?? (fieldDef.id != null ? String(fieldDef.id) : rawKey)
}

export default function TicketDetailPage() {
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const isZh = locale === 'zh'
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const ticketId = Number(params.id)
  const fromList = searchParams.get('from') === 'list'
  const canEditTicket = hasPermission(currentUser, 'ticket.workspace.edit')
  const canCommentTicket = hasPermission(currentUser, 'ticket.workspace.comment')

  // ── Data fetching ──
  const { data: ticket, isLoading } = useTicket(ticketId)
  const { data: layout } = useFormLayoutByScene('ticket_detail')
  const { data: rulesData } = useInteractionRules(layout?.id)

  // Fetch related user & organization
  const { data: relatedUser } = useUser(ticket?.user_id ?? 0)
  const { data: relatedOrg } = useOrganization(relatedUser?.organization_id ?? 0)

  // Fetch unified field defs for ALL domains referenced in the layout
  const fieldsLocale = isZh ? 'zh' : 'en'
  const { data: ticketFields } = useUnifiedFields({ domain: 'ticket', include_metadata: true, locale: fieldsLocale })
  const { data: userFields } = useUnifiedFields({ domain: 'user', include_metadata: false, locale: fieldsLocale })
  const { data: orgFields } = useUnifiedFields({ domain: 'organization', include_metadata: false, locale: fieldsLocale })
  const { data: sharedFields } = useUnifiedFields({ domain: 'shared_pool', include_metadata: false, locale: fieldsLocale })

  const updateTicket = useUpdateTicket()

  const rules: FdInteractionRule[] = useMemo(
    () => (rulesData?.items ?? []).filter((r) => r.is_enabled).sort((a, b) => a.sort_order - b.sort_order),
    [rulesData],
  )

  const { fieldDefMap, ticketChangeFieldDefMap } = useMemo(() => {
    const byRef = new Map<string, UnifiedField>()
    const changeMap = new Map<string, UnifiedField>()
    const all = [
      ...(ticketFields?.items ?? []),
      ...(userFields?.items ?? []),
      ...(orgFields?.items ?? []),
      ...(sharedFields?.items ?? []),
    ]
    for (const f of all) {
      registerFieldLookup(byRef, f)

      if (fieldAppliesToTicket(f)) {
        if (f.key) changeMap.set(f.key, f)
        if (f.slot_column) changeMap.set(f.slot_column, f)
        if (f.id != null) changeMap.set(String(f.id), f)
      }
    }
    return { fieldDefMap: byRef, ticketChangeFieldDefMap: changeMap }
  }, [ticketFields, userFields, orgFields, sharedFields])

  const resolveTicketScopedFieldDef = useCallback(
    (fieldKey: string) => ticketChangeFieldDefMap.get(fieldKey),
    [ticketChangeFieldDefMap],
  )

  // ── Build a flat value map from ticket + related user + related org ──
  const fieldValues = useMemo(() => {
    const vals: Record<string, unknown> = {}
    if (!ticket) return vals

    // Ticket system fields
    const ticketObj = ticket as Record<string, unknown>
    for (const k of [
      'title',
      'description',
      'status',
      'priority',
      'ticket_number',
      'conversation_id',
      'call_record_id',
      'user_id',
      'agent_id',
      'assignee_group_id',
      'created_by',
      'updated_by',
      'created_at',
      'updated_at',
    ]) {
      if (ticketObj[k] != null) vals[`ticket:${k}`] = ticketObj[k]
    }
    if (ticket.agent_id != null) vals['ticket:assignee'] = ticket.agent_id
    if (ticket.assignee_group_id != null) vals['ticket:assignee_group'] = ticket.assignee_group_id
    // Ticket custom fields
    if (ticket.custom_fields) {
      for (const [k, v] of Object.entries(ticket.custom_fields)) {
        if (v != null) addScopedCustomFieldValueAliases(vals, 'ticket', 'ticket', k, v, fieldDefMap)
      }
    }

    // User fields
    if (relatedUser) {
      const userObj = relatedUser as Record<string, unknown>
      for (const k of ['name', 'email', 'phone', 'gender', 'address', 'remark', 'external_id', 'nickname', 'created_by', 'updated_by']) {
        if (userObj[k] != null) vals[`user:${k}`] = userObj[k]
      }
      if (relatedUser.custom_fields) {
        for (const [k, v] of Object.entries(relatedUser.custom_fields)) {
          if (v != null) addScopedCustomFieldValueAliases(vals, 'user', 'user', k, v, fieldDefMap)
        }
      }
    }

    // Organization fields
    if (relatedOrg) {
      const orgObj = relatedOrg as Record<string, unknown>
      for (const k of ['name', 'description', 'created_by', 'updated_by']) {
        if (orgObj[k] != null) vals[`org:${k}`] = orgObj[k]
      }
      if (relatedOrg.custom_fields) {
        for (const [k, v] of Object.entries(relatedOrg.custom_fields)) {
          if (v != null) addScopedCustomFieldValueAliases(vals, 'org', 'organization', k, v, fieldDefMap)
        }
      }
    }

    return vals
  }, [ticket, relatedUser, relatedOrg, fieldDefMap])

  // Editable form state (only for ticket-source editable fields)
  const [editValues, setEditValues] = useState<Record<string, unknown>>({})
  const [collapsedTabs, setCollapsedTabs] = useState<Set<number>>(new Set())
  const [collapsedSections, setCollapsedSections] = useState<Set<number>>(new Set())
  const [saving, setSaving] = useState(false)
  const [saveToast, setSaveToast] = useState<'success' | 'error' | null>(null)
  const [rightTab, setRightTab] = useState<'comments' | 'changes' | 'all'>('comments')
  const [editingFieldId, setEditingFieldId] = useState<number | null>(null)
  const [selectedSessionRecordId, setSelectedSessionRecordId] = useState<number | null>(null)
  const [selectedCallRecordId, setSelectedCallRecordId] = useState<number | null>(null)
  const shouldLoadChanges = rightTab === 'changes' || rightTab === 'all'
  const changeQueryParams = useMemo(() => ({ page: 1, per_page: 50 }), [])
  const {
    data: changesData,
    isLoading: changesLoading,
    isError: changesError,
  } = useTicketChanges(ticketId, changeQueryParams, shouldLoadChanges)

  useEffect(() => {
    if (!ticket) return
    const vals: Record<string, unknown> = {}
    for (const k of ['title', 'description', 'status', 'priority', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id', 'created_by', 'updated_by']) {
      const v = (ticket as Record<string, unknown>)[k]
      if (v != null) vals[k] = v
    }
    if (ticket.agent_id != null) vals.assignee = ticket.agent_id
    if (ticket.assignee_group_id != null) vals.assignee_group = ticket.assignee_group_id
    if (ticket.custom_fields) {
      for (const [k, v] of Object.entries(ticket.custom_fields)) {
        if (v != null) addTicketEditValueAliases(vals, k, v, fieldDefMap)
      }
    }
    setEditValues(vals)
  }, [ticket, fieldDefMap])

  // ── Layout ──
  const tabs = useMemo(() => {
    if (!layout?.tabs) return []
    return [...layout.tabs].sort((a, b) => a.sort_order - b.sort_order)
  }, [layout])

  const setEditFieldValue = useCallback((key: string, value: unknown) => {
    setEditValues((prev) => {
      const next = { ...prev }
      addTicketEditValueAliases(next, key, value, fieldDefMap)
      return next
    })
  }, [fieldDefMap])

  const toggleTab = useCallback((tabId: number) => {
    setCollapsedTabs((prev) => {
      const next = new Set(prev)
      if (next.has(tabId)) next.delete(tabId)
      else next.add(tabId)
      return next
    })
  }, [])

  const toggleSection = useCallback((sectionId: number) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(sectionId)) next.delete(sectionId)
      else next.add(sectionId)
      return next
    })
  }, [])

  // Resolve the field key considering field_source
  const getFieldKey = useCallback((field: FdFormLayoutField): string => {
    if (field.field_key) return field.field_key
    if (field.field_definition_id) return String(field.field_definition_id)
    return `field_${field.id}`
  }, [])

  const getFieldDef = useCallback((field: FdFormLayoutField): UnifiedField | undefined => {
    const domain = unifiedDomainForLayoutFieldSource(field.field_source)
    if (field.field_key) return fieldDefMap.get(`${domain}:${field.field_key}`)
    if (field.field_definition_id != null) return fieldDefMap.get(`${domain}:${field.field_definition_id}`)
    return undefined
  }, [fieldDefMap])

  // Get the display value for a field, considering its source
  const getFieldValue = useCallback((field: FdFormLayoutField): unknown => {
    const key = getFieldKey(field)
    const src = field.field_source

    if (src === 'user') return fieldValues[`user:${key}`]
    if (src === 'organization') return fieldValues[`org:${key}`]
    // ticket source: use editValues for editable, fieldValues for display
    return editValues[key] ?? fieldValues[`ticket:${key}`]
  }, [getFieldKey, fieldValues, editValues])

  const computedFieldStates = useMemo(() => {
    const states = new Map<string, FieldState>()
    for (const tab of tabs) {
      for (const section of (tab.sections ?? [])) {
        for (const field of (section.fields ?? [])) {
          states.set(`${field.field_source}:${getFieldKey(field)}`, field.default_state as FieldState)
        }
      }
    }
    for (const rule of rules) {
      const met = evaluateConditions(rule.conditions, rule.condition_logic, editValues)
      if (met) {
        for (const action of rule.actions) {
          const targetKey = action.target_field_key ?? (action.target_field_id ? String(action.target_field_id) : null)
          if (targetKey) states.set(`ticket:${targetKey}`, action.state)
        }
      }
    }
    return states
  }, [tabs, rules, editValues, getFieldKey])

  const getState = useCallback((field: FdFormLayoutField): FieldState => {
    const compositeKey = `${field.field_source}:${getFieldKey(field)}`
    return computedFieldStates.get(compositeKey) ?? field.default_state as FieldState
  }, [computedFieldStates, getFieldKey])

  const handleSave = useCallback(async () => {
    if (saving) return
    setSaving(true)
    try {
      const systemFields = ['title', 'description', 'status', 'priority', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id']
      const payload: Record<string, unknown> = {}
      const customFields: Record<string, CustomFieldValue> = {}

      for (const [key, value] of Object.entries(editValues)) {
        if (key === 'ticket_number') continue
        if (key === 'created_by' || key === 'updated_by') continue
        const payloadKey = key === 'assignee' ? 'agent_id' : key === 'assignee_group' ? 'assignee_group_id' : key
        if (systemFields.includes(payloadKey)) {
          payload[payloadKey] = value
        } else {
          customFields[ticketPayloadFieldKey(payloadKey, fieldDefMap)] = value as CustomFieldValue
        }
      }

      await updateTicket.mutateAsync({
        id: ticketId,
        data: {
          title: payload.title as string | undefined,
          description: payload.description as string | undefined,
          status: payload.status as string | undefined,
          priority: payload.priority as string | undefined,
          conversation_id: payload.conversation_id as number | undefined,
          call_record_id: payload.call_record_id as number | undefined,
          user_id: payload.user_id as number | undefined,
          agent_id: payload.agent_id as number | undefined,
          assignee_group_id: payload.assignee_group_id as number | undefined,
          custom_fields: customFields,
        },
      })
      setEditingFieldId(null)
      setSaveToast('success')
      window.setTimeout(() => setSaveToast(null), 3000)
    } catch {
      setSaveToast('error')
      window.setTimeout(() => setSaveToast(null), 3000)
    } finally {
      setSaving(false)
    }
  }, [saving, editValues, ticketId, updateTicket, fieldDefMap])

  const columnsPerRow = layout?.columns_per_row ?? 2
  const labelPosition = layout?.label_position ?? 'top'

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    )
  }

  if (!ticket) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{isZh ? '工单不存在' : 'Ticket not found'}</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header — success/error toast is absolutely centered in this bar (no layout shift) */}
      <div className="relative flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div className="relative z-20 flex min-w-0 flex-1 items-center gap-3.5 pr-4">
          <button
            onClick={() => fromList ? router.back() : router.push('/workspace/tickets')}
            className="flex shrink-0 items-center text-foreground/80 transition-colors hover:text-foreground"
          >
            <IconArrowLeft size={20} />
          </button>
          <h2 className="min-w-0 truncate text-lg font-semibold text-foreground">{ticket.title}</h2>
        </div>

        {saveToast && (
          <div
            className={cn(
              'pointer-events-none absolute left-1/2 top-1/2 z-10 max-w-[min(90%,360px)] -translate-x-1/2 -translate-y-1/2 truncate rounded-lg border px-4 py-2 text-center text-sm font-medium shadow-lg',
              saveToast === 'success'
                ? 'border-green-600 bg-green-600 text-white'
                : 'border-red-600 bg-red-600 text-white',
            )}
            role="status"
            aria-live="polite"
          >
            {saveToast === 'success'
              ? (isZh ? '保存成功' : 'Saved successfully')
              : (isZh ? '保存失败，请重试' : 'Save failed. Please try again.')}
          </div>
        )}

        {canEditTicket && (
          <button
            onClick={handleSave}
            disabled={saving}
            className="relative z-20 h-9 shrink-0 rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? (isZh ? '保存中...' : 'Saving...') : (isZh ? '保存' : 'Save')}
          </button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left: layout-driven form */}
        <div
          className="min-h-0 w-[min(100%,50rem)] shrink-0 flex-none overflow-y-auto bg-white"
          onClick={(e) => {
            // Click on blank area to dismiss editing
            if (e.target === e.currentTarget) setEditingFieldId(null)
          }}
        >
          <div className="px-6 py-[18px]">
            {!layout ? (
              <p className="text-sm text-muted-foreground">
                {isZh ? '未配置工单详情布局' : 'No detail layout configured'}
              </p>
            ) : (
              <div className="flex flex-col gap-[18px]">
                {tabs.map((tab) => (
                  <TabBlock
                    key={tab.id}
                    tab={tab}
                    columnsPerRow={columnsPerRow}
                    labelPosition={labelPosition}
                    getFieldKey={getFieldKey}
                    getFieldDef={getFieldDef}
                    getFieldValue={getFieldValue}
                    getState={getState}
                    editValues={editValues}
                    setEditFieldValue={setEditFieldValue}
                    collapsed={collapsedTabs.has(tab.id)}
                    onToggleTab={() => toggleTab(tab.id)}
                    collapsedSections={collapsedSections}
                    onToggleSection={toggleSection}
                    editingFieldId={editingFieldId}
                    onStartEdit={canEditTicket ? setEditingFieldId : () => undefined}
                    onOpenSessionDrawer={setSelectedSessionRecordId}
                    onOpenCallDrawer={setSelectedCallRecordId}
                    conversationPublicId={ticket.conversation_public_id ?? ticket.call_record_call_id ?? undefined}
                    callRecordId={ticket.call_record_id ?? undefined}
                    isZh={isZh}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: activity panel (flexible width, matches design) */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col border-l border-border bg-[#f5f5f5]">
          <div className="flex shrink-0 items-end justify-start gap-4 px-5 pt-1">
            {(['comments', 'changes', 'all'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setRightTab(t)}
                className={cn(
                  'shrink-0 border-b-2 border-transparent pb-3 pt-2 text-xs transition-colors',
                  rightTab === t
                    ? 'border-foreground font-semibold text-foreground'
                    : 'font-normal text-muted-foreground hover:text-foreground/80',
                )}
              >
                {t === 'comments' ? (isZh ? '评论' : 'Comments')
                  : t === 'changes' ? (isZh ? '变更记录' : 'Changes')
                  : (isZh ? '全部' : 'All')}
              </button>
            ))}
          </div>

          {rightTab === 'changes' ? (
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <TicketChangeTimeline
                changes={changesData?.items ?? []}
                isLoading={changesLoading}
                isError={changesError}
                isZh={isZh}
                resolveFieldDef={resolveTicketScopedFieldDef}
                emptyText={isZh ? '暂无变更记录' : 'No changes yet'}
              />
            </div>
          ) : (
            <TicketCommentThread
              ticketId={ticketId}
              isZh={isZh}
              mergeWithChanges={rightTab === 'all'}
              changes={changesData?.items ?? []}
              changesLoading={changesLoading}
              changesError={changesError}
              renderChange={(change) => (
                <TicketChangeCard
                  change={change}
                  isZh={isZh}
                  resolveFieldDef={resolveTicketScopedFieldDef}
                  showKindBadge={rightTab === 'all'}
                />
              )}
              showComposer={rightTab === 'comments' && canCommentTicket}
              emptyText={
                rightTab === 'comments'
                  ? (isZh ? '暂无评论' : 'No comments yet')
                  : (isZh ? '暂无动态记录' : 'No activity yet')
              }
              className="min-h-0 flex-1"
            />
          )}
        </div>
      </div>

      {selectedSessionRecordId != null && (
        <SessionDetailDrawer
          recordId={selectedSessionRecordId}
          onClose={() => setSelectedSessionRecordId(null)}
        />
      )}
      {selectedCallRecordId != null && (
        <CallRecordDetailDrawer
          recordId={selectedCallRecordId}
          onClose={() => setSelectedCallRecordId(null)}
        />
      )}
    </div>
  )
}

function TicketChangeTimeline({
  changes,
  isLoading,
  isError,
  isZh,
  resolveFieldDef,
  emptyText,
}: {
  changes: TicketChange[]
  isLoading: boolean
  isError: boolean
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
  emptyText: string
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-muted-foreground">
          {isZh ? '加载变更记录中...' : 'Loading changes...'}
        </p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-destructive">
          {isZh ? '变更记录加载失败' : 'Failed to load changes'}
        </p>
      </div>
    )
  }

  if (changes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-muted-foreground">{emptyText}</p>
      </div>
    )
  }

  return (
    <ActivityTimeline>
      {changes.map((change) => (
        <ActivityTimelineRow key={change.id}>
          <TicketChangeCard
            change={change}
            isZh={isZh}
            resolveFieldDef={resolveFieldDef}
          />
        </ActivityTimelineRow>
      ))}
    </ActivityTimeline>
  )
}

function TicketChangeCard({
  change,
  isZh,
  resolveFieldDef,
  showKindBadge = false,
}: {
  change: TicketChange
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
  /** When true (e.g. "All" activity tab), show a pill after the actor name. */
  showKindBadge?: boolean
}) {
  const actorName = getChangeActorName(change, isZh)
  const isCreateRecord = change.field_key === TICKET_CHANGE_CREATE_FIELD_KEY
  const entryGroups = change.entries && change.entries.length > 0
    ? getTicketChangeEntryGroups(change.entries, isZh)
    : []

  return (
    <div className="min-w-0 rounded-lg bg-white px-4 py-3.5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <ActivityActorAvatar name={actorName} src={change.actor_avatar} />
          <span className="min-w-0 truncate text-[13px] text-foreground">
            {actorName}
          </span>
          {showKindBadge && (
            <span className="shrink-0 rounded-md border border-border bg-muted/50 px-1.5 py-px text-[10px] leading-tight text-muted-foreground">
              {isZh ? '变更记录' : 'Changes'}
            </span>
          )}
        </div>
        <time
          className="shrink-0 text-xs text-muted-foreground"
          dateTime={change.created_at}
        >
          {formatChangeTime(change.created_at, isZh)}
        </time>
      </div>
      {entryGroups.length > 0 ? (
        <div className="flex flex-col gap-3">
          {entryGroups.map((group) => (
            <div key={group.source} className="flex flex-col gap-2.5">
              {(entryGroups.length > 1 || group.source === TICKET_WORKFLOW_FIELD_SOURCE) && (
                <div className="text-[11px] font-medium text-muted-foreground">
                  {group.label}
                </div>
              )}
              {group.entries.map((entry, idx) => (
                <TicketChangeEntryLine
                  key={`${change.id}-${group.source}-${entry.field_key}-${idx}`}
                  entry={entry}
                  isCreateRecord={isCreateRecord}
                  isZh={isZh}
                  resolveFieldDef={resolveFieldDef}
                />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="min-w-0 text-xs text-foreground">
          <span>{change.field_label}</span>
          <span className="mx-1">{isZh ? '从' : 'from'}</span>
          <ChangeValuePill
            value={change.old_value}
            fieldKey={change.field_key}
            fieldDef={resolveFieldDef(change.field_key)}
            isZh={isZh}
          />
          <span className="mx-1">{isZh ? '变更为' : 'to'}</span>
          <ChangeValuePill
            value={change.new_value}
            fieldKey={change.field_key}
            fieldDef={resolveFieldDef(change.field_key)}
            isZh={isZh}
          />
        </div>
      )}
    </div>
  )
}

function TicketChangeEntryLine({
  entry,
  isCreateRecord,
  isZh,
  resolveFieldDef,
}: {
  entry: TicketChangeEntry
  isCreateRecord: boolean
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
}) {
  return (
    <div className="min-w-0 text-xs leading-relaxed text-foreground">
      {isCreateRecord ? (
        <>
          <span>{entry.field_label}</span>
          <span className="mx-1">:</span>
          <ChangeValuePill
            value={entry.new_value}
            fieldKey={entry.field_key}
            fieldDef={resolveFieldDef(entry.field_key)}
            isZh={isZh}
          />
        </>
      ) : (
        <>
          <span>{entry.field_label}</span>
          <span className="mx-1">{isZh ? '从' : 'from'}</span>
          <ChangeValuePill
            value={entry.old_value}
            fieldKey={entry.field_key}
            fieldDef={resolveFieldDef(entry.field_key)}
            isZh={isZh}
          />
          <span className="mx-1">{isZh ? '变更为' : 'to'}</span>
          <ChangeValuePill
            value={entry.new_value}
            fieldKey={entry.field_key}
            fieldDef={resolveFieldDef(entry.field_key)}
            isZh={isZh}
          />
        </>
      )}
    </div>
  )
}

function getTicketChangeEntryGroups(entries: TicketChangeEntry[], isZh: boolean) {
  const employeeEntries = entries.filter((entry) => entry.field_source !== TICKET_WORKFLOW_FIELD_SOURCE)
  const workflowEntries = entries.filter((entry) => entry.field_source === TICKET_WORKFLOW_FIELD_SOURCE)
  return [
    employeeEntries.length > 0
      ? {
          source: 'employee',
          label: isZh ? '员工改动' : 'Employee changes',
          entries: employeeEntries,
        }
      : null,
    workflowEntries.length > 0
      ? {
          source: 'ticket_workflow',
          label: isZh ? '工单流程改动' : 'Ticket workflow changes',
          entries: workflowEntries,
        }
      : null,
  ].filter((group): group is { source: string; label: string; entries: TicketChangeEntry[] } => group != null)
}

function ChangeValuePill({
  value,
  fieldKey,
  fieldDef,
  isZh,
}: {
  value: TicketChangeValue
  fieldKey: string
  fieldDef: UnifiedField | undefined
  isZh: boolean
}) {
  if (fieldKey === 'user_id' || fieldDef?.field_type === FieldType.USER_SELECT) {
    return <UserChangeValue value={value} isZh={isZh} />
  }
  if (
    fieldKey === 'agent_id'
    || fieldKey === 'assignee'
    || fieldDef?.field_type === FieldType.EMPLOYEE_SELECT
  ) {
    return <EmployeeChangeValue value={value} isZh={isZh} />
  }
  if (
    fieldKey === 'assignee_group_id'
    || fieldKey === 'assignee_group'
    || fieldDef?.field_type === FieldType.GROUP_SELECT
  ) {
    return <EmployeeGroupChangeValue value={value} isZh={isZh} />
  }

  return (
    <span className="inline-block max-w-full whitespace-pre-wrap break-words rounded-md bg-muted px-1.5 py-0.5 align-top [overflow-wrap:anywhere]">
      {formatChangeValue(value, fieldKey, fieldDef, isZh)}
    </span>
  )
}

function UserChangeValue({
  value,
  isZh,
}: {
  value: TicketChangeValue
  isZh: boolean
}) {
  const userValue = parseUserChangeValue(value)
  const { data: user } = useUser(userValue?.id ?? 0)

  if (!userValue) {
    return <span className="rounded-md bg-muted px-1.5 py-0.5">-</span>
  }

  const label = user?.name?.trim() || userValue.name || (isZh ? `用户 #${userValue.id}` : `User #${userValue.id}`)

  return (
    <Link
      href={`/workspace/users/${user?.public_id || userValue.id}`}
      className="rounded-md bg-muted px-1.5 py-0.5 font-medium text-primary underline-offset-2 hover:underline"
    >
      {label}
    </Link>
  )
}

function parseUserChangeValue(
  value: TicketChangeValue,
): { id: number; name?: string } | null {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return { id: value }
  }
  if (typeof value === 'string') {
    const id = Number(value)
    return Number.isFinite(id) && id > 0 ? { id } : null
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const rawId = (value as { id?: unknown; user_id?: unknown }).id
      ?? (value as { user_id?: unknown }).user_id
    const id = typeof rawId === 'number' ? rawId : Number(rawId)
    if (!Number.isFinite(id) || id <= 0) return null

    const rawName = (value as { name?: unknown; user_name?: unknown }).name
      ?? (value as { user_name?: unknown }).user_name
    const name = typeof rawName === 'string' && rawName.trim()
      ? rawName.trim()
      : undefined
    return { id, name }
  }
  return null
}

function EmployeeChangeValue({
  value,
  isZh,
}: {
  value: TicketChangeValue
  isZh: boolean
}) {
  const parsed = parseEmployeeChangeValue(value)
  const { data: employee } = useEmployee(parsed?.id ?? 0)

  if (!parsed) {
    return <span className="rounded-md bg-muted px-1.5 py-0.5">-</span>
  }

  const label =
    employee?.nickname?.trim()
    || employee?.name?.trim()
    || employee?.username?.trim()
    || parsed.name
    || (isZh ? `员工 #${parsed.id}` : `Employee #${parsed.id}`)

  return (
    <Link
      href={`/employees/${parsed.id}`}
      className="rounded-md bg-muted px-1.5 py-0.5 font-medium text-primary underline-offset-2 hover:underline"
    >
      {label}
    </Link>
  )
}

function EmployeeGroupChangeValue({
  value,
  isZh,
}: {
  value: TicketChangeValue
  isZh: boolean
}) {
  const groupId = parseEmployeeGroupChangeValue(value)
  const { data: group } = useEmployeeGroup(groupId ?? 0)

  if (groupId == null) {
    return <span className="rounded-md bg-muted px-1.5 py-0.5">-</span>
  }

  const label =
    group?.name?.trim()
    || (isZh ? `负责组 #${groupId}` : `Group #${groupId}`)

  return (
    <Link
      href={`/employee-groups/${groupId}`}
      className="rounded-md bg-muted px-1.5 py-0.5 font-medium text-primary underline-offset-2 hover:underline"
    >
      {label}
    </Link>
  )
}

function parseEmployeeChangeValue(
  value: TicketChangeValue,
): { id: number; name?: string } | null {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 0 ? { id: value } : null
  }
  if (typeof value === 'string') {
    const id = Number(value)
    return Number.isFinite(id) && id > 0 ? { id } : null
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const rawId = (value as { id?: unknown; agent_id?: unknown }).id
      ?? (value as { agent_id?: unknown }).agent_id
    const id = typeof rawId === 'number' ? rawId : Number(rawId)
    if (!Number.isFinite(id) || id <= 0) return null

    const rawName = (value as { name?: unknown; nickname?: unknown }).name
      ?? (value as { nickname?: unknown }).nickname
    const name = typeof rawName === 'string' && rawName.trim()
      ? rawName.trim()
      : undefined
    return { id, name }
  }
  return null
}

function parseEmployeeGroupChangeValue(value: TicketChangeValue): number | null {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 0 ? value : null
  }
  if (typeof value === 'string') {
    const id = Number(value)
    return Number.isFinite(id) && id > 0 ? id : null
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const rawId = (value as { id?: unknown; assignee_group_id?: unknown }).id
      ?? (value as { assignee_group_id?: unknown }).assignee_group_id
    const id = typeof rawId === 'number' ? rawId : Number(rawId)
    if (!Number.isFinite(id) || id <= 0) return null
    return id
  }
  return null
}

function formatChangeTime(value: string, isZh: boolean): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function getChangeActorName(change: TicketChange, isZh: boolean): string {
  if (change.actor_type === 'user' && change.actor_id != null) {
    return change.actor_name?.trim() || (isZh ? '未命名' : 'Unnamed')
  }
  return change.actor_name?.trim() || (isZh ? '系统' : 'System')
}

function formatChangeValue(
  value: TicketChangeValue,
  fieldKey: string,
  fieldDef: UnifiedField | undefined,
  isZh: boolean,
): string {
  if (value == null || value === '') return '-'
  const raw = String(value)

  const fieldType = fieldDef?.field_type
  if (fieldDef?.type_config?.value_kind === 'actor') {
    return formatActorFieldValue(value)
  }
  if (fieldType === 'rich_text') {
    const plain = richTextToPlainCell(value, fieldDef?.type_config)
    return plain === '' ? '-' : plain
  }

  const selectLookup = buildSelectLookup(fieldDef)
  if (selectLookup) {
    if (Array.isArray(value)) {
      if (value.length === 0) return '-'
      return value
        .map((item) => {
          const s = typeof item === 'object' && item != null
            ? JSON.stringify(item)
            : String(item)
          return applySelectLookupString(s, selectLookup)
        })
        .join(isZh ? '、' : ', ')
    }
    if (typeof value === 'string' || typeof value === 'number') {
      return applySelectLookupString(String(value), selectLookup)
    }
  }

  if (typeof value === 'boolean') return isZh ? (value ? '是' : '否') : (value ? 'Yes' : 'No')
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    return value.map((item) => {
      if (item && typeof item === 'object' && 'name' in item) {
        const name = (item as { name?: unknown }).name
        return typeof name === 'string' ? name : JSON.stringify(item)
      }
      return typeof item === 'object' ? JSON.stringify(item) : String(item)
    }).join('、')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return raw
}

function applySelectLookupString(raw: string, selectLookup: Map<string, string>): string {
  if (raw.includes(',')) {
    return raw
      .split(',')
      .map((v) => selectLookup.get(v.trim()) ?? v.trim())
      .join(', ')
  }
  return selectLookup.get(raw) ?? raw
}

// ── Tab block: renders a tab as a collapsible section ──

function TabBlock({
  tab,
  columnsPerRow,
  labelPosition,
  getFieldKey,
  getFieldDef,
  getFieldValue,
  getState,
  editValues,
  setEditFieldValue,
  collapsed,
  onToggleTab,
  collapsedSections,
  onToggleSection,
  editingFieldId,
  onStartEdit,
  onOpenSessionDrawer,
  onOpenCallDrawer,
  conversationPublicId,
  callRecordId,
  isZh,
}: {
  tab: FdFormLayoutTab
  columnsPerRow: number
  labelPosition: string
  getFieldKey: (f: FdFormLayoutField) => string
  getFieldDef: (f: FdFormLayoutField) => UnifiedField | undefined
  getFieldValue: (f: FdFormLayoutField) => unknown
  getState: (f: FdFormLayoutField) => FieldState
  editValues: Record<string, unknown>
  setEditFieldValue: (key: string, val: unknown) => void
  collapsed: boolean
  onToggleTab: () => void
  collapsedSections: Set<number>
  onToggleSection: (id: number) => void
  editingFieldId: number | null
  onStartEdit: (id: number | null) => void
  onOpenSessionDrawer: (recordId: number) => void
  onOpenCallDrawer: (recordId: number) => void
  conversationPublicId?: string
  callRecordId?: number
  isZh: boolean
}) {
  const sections = useMemo(
    () => [...(tab.sections ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [tab.sections],
  )

  // Collect all visible fields across sections to check if tab has any content
  const hasVisibleFields = useMemo(() => {
    for (const section of sections) {
      for (const field of (section.fields ?? [])) {
        if (getState(field) !== 'hidden') return true
      }
    }
    return false
  }, [sections, getState])

  if (!hasVisibleFields) return null

  return (
    <div>
      {/* Tab header - acts as collapsible section title */}
      <button
        onClick={onToggleTab}
        className="flex w-full items-center gap-2.5 pb-3 text-left"
        style={{ borderBottom: '1px solid #E8E8E8' }}
      >
        {collapsed
          ? <IconChevronRight size={18} className="shrink-0 text-muted-foreground" />
          : <IconChevronDown size={18} className="shrink-0 text-muted-foreground" />}
        <span className="text-[15px] font-semibold text-foreground">{tab.name}</span>
      </button>

      {!collapsed && (
        <div className="pt-3">
          {sections.map((section) => (
            <SectionBlock
              key={section.id}
              section={section}
              columnsPerRow={columnsPerRow}
              labelPosition={labelPosition}
              getFieldKey={getFieldKey}
              getFieldDef={getFieldDef}
              getFieldValue={getFieldValue}
              getState={getState}
              editValues={editValues}
              setEditFieldValue={setEditFieldValue}
              collapsed={collapsedSections.has(section.id)}
              onToggle={() => onToggleSection(section.id)}
              editingFieldId={editingFieldId}
              onStartEdit={onStartEdit}
              onOpenSessionDrawer={onOpenSessionDrawer}
              onOpenCallDrawer={onOpenCallDrawer}
              conversationPublicId={conversationPublicId}
              callRecordId={callRecordId}
              isZh={isZh}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Section block ──

function SectionBlock({
  section,
  columnsPerRow,
  labelPosition,
  getFieldKey,
  getFieldDef,
  getFieldValue,
  getState,
  editValues,
  setEditFieldValue,
  collapsed,
  onToggle,
  editingFieldId,
  onStartEdit,
  onOpenSessionDrawer,
  onOpenCallDrawer,
  conversationPublicId,
  callRecordId,
  isZh,
}: {
  section: FdFormLayoutSection
  columnsPerRow: number
  labelPosition: string
  getFieldKey: (f: FdFormLayoutField) => string
  getFieldDef: (f: FdFormLayoutField) => UnifiedField | undefined
  getFieldValue: (f: FdFormLayoutField) => unknown
  getState: (f: FdFormLayoutField) => FieldState
  editValues: Record<string, unknown>
  setEditFieldValue: (key: string, val: unknown) => void
  collapsed: boolean
  onToggle: () => void
  editingFieldId: number | null
  onStartEdit: (id: number | null) => void
  onOpenSessionDrawer: (recordId: number) => void
  onOpenCallDrawer: (recordId: number) => void
  conversationPublicId?: string
  callRecordId?: number
  isZh: boolean
}) {
  const fields = useMemo(
    () => [...(section.fields ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [section.fields],
  )

  const visibleFields = useMemo(
    () => fields.filter((f) => getState(f) !== 'hidden'),
    [fields, getState],
  )

  if (visibleFields.length === 0) return null

  const hasName = !!section.name

  return (
    <div className={hasName ? 'mt-4' : ''}>
      {/* Named section: show sub-section header with vertical bar */}
      {hasName && (
        <button
          onClick={onToggle}
          className="flex w-full items-center gap-2.5 pb-3.5 text-left"
        >
          <div className="h-4 w-[3px] rounded-full bg-primary" />
          <span className="text-sm font-semibold text-foreground">{section.name}</span>
        </button>
      )}

      {(!hasName || !collapsed) && (
        <div>
          <div
            className="grid gap-x-4 gap-y-3.5"
            style={{ gridTemplateColumns: `repeat(${columnsPerRow}, minmax(0, 1fr))` }}
          >
            {visibleFields.map((field) => {
              const def = getFieldDef(field)
              const value = getFieldValue(field)
              const state = getState(field)
              const span = Math.min(field.column_span, columnsPerRow)

              return (
                <div key={field.id} style={{ gridColumn: `span ${span} / span ${span}` }}>
                  <FieldDisplay
                    field={field}
                    fieldDef={def}
                    fieldKey={getFieldKey(field)}
                    value={value}
                    displayValueOverride={
                      field.field_source === 'ticket' && getFieldKey(field) === 'conversation_id'
                        ? conversationPublicId
                        : undefined
                    }
                    state={state}
                    onChange={(val) => setEditFieldValue(getFieldKey(field), val)}
                    editValues={editValues}
                    labelPosition={labelPosition}
                    isEditing={editingFieldId === field.id}
                    onStartEdit={() => onStartEdit(field.id)}
                    onStopEdit={() => onStartEdit(null)}
                    onOpenSessionDrawer={onOpenSessionDrawer}
                    onOpenCallDrawer={onOpenCallDrawer}
                    callRecordId={callRecordId}
                    isZh={isZh}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Field display — click-to-edit ──

const FIELD_KEY_TYPE_MAP: Record<string, string> = {
  user_id: FieldType.USER_SELECT,
  assignee: FieldType.EMPLOYEE_SELECT,
  agent_id: FieldType.EMPLOYEE_SELECT,
  assignee_group: FieldType.GROUP_SELECT,
  assignee_group_id: FieldType.GROUP_SELECT,
}

function inferFieldTypeFromKey(fieldKey: string): string {
  return FIELD_KEY_TYPE_MAP[fieldKey] ?? FieldType.SINGLE_LINE_TEXT
}

function FieldDisplay({
  field,
  fieldDef,
  fieldKey,
  value,
  displayValueOverride,
  state,
  onChange,
  editValues,
  labelPosition,
  isEditing,
  onStartEdit,
  onStopEdit,
  onOpenSessionDrawer,
  onOpenCallDrawer,
  callRecordId,
  isZh,
}: {
  field: FdFormLayoutField
  fieldDef: UnifiedField | undefined
  fieldKey: string
  value: unknown
  displayValueOverride?: string
  state: FieldState
  onChange: (val: unknown) => void
  editValues: Record<string, unknown>
  labelPosition: string
  isEditing: boolean
  onStartEdit: () => void
  onStopEdit: () => void
  onOpenSessionDrawer: (recordId: number) => void
  onOpenCallDrawer: (recordId: number) => void
  callRecordId?: number
  isZh: boolean
}) {
  const label = fieldDef?.name ?? fieldKey
  const isRequired = state === 'required'
  const isReadOnlyByConfig = fieldDef?.type_config?.readonly === true
  const isEditable = (state === 'optional' || state === 'required') && field.field_source === 'ticket' && fieldKey !== 'conversation_id' && !isReadOnlyByConfig
  const fieldType = fieldDef?.field_type ?? inferFieldTypeFromKey(fieldKey)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(null)

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isEditing])

  const strVal = value != null ? String(value) : ''
  const isLongTextField = fieldType === 'multi_line_text' || fieldType === 'rich_text'
  const isUserSelect = fieldType === FieldType.USER_SELECT || fieldKey === 'user_id'
  const isEmployeeSelect = fieldType === FieldType.EMPLOYEE_SELECT || fieldKey === 'assignee'
  const isGroupSelect = fieldType === FieldType.GROUP_SELECT || fieldKey === 'assignee_group'
  const isConversationField = field.field_source === 'ticket' && fieldKey === 'conversation_id'
  const numericUserId =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value)
        : 0
  const userId = Number.isFinite(numericUserId) ? numericUserId : 0
  const { data: selectedUser } = useUser(isUserSelect && userId > 0 ? userId : 0)
  const numericEntityId =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim()
        ? Number(value)
        : 0
  const entityId = Number.isFinite(numericEntityId) ? numericEntityId : 0
  const { data: selectedEmployee } = useEmployee(isEmployeeSelect && entityId > 0 ? entityId : 0)
  const { data: selectedGroup } = useEmployeeGroup(isGroupSelect && entityId > 0 ? entityId : 0)

  const pillOptions: FieldSelectOption[] = useMemo(() => {
    if (fieldType === 'single_select' || fieldType === 'multi_select') {
      if (fieldDef) {
        return coalescePillOptions(fieldDef.options ?? [], fieldDef.type_config)
      }
      return []
    }
    if (fieldDef?.tree_nodes?.length) {
      return fieldDef.tree_nodes
        .filter((n) => n.is_active)
        .sort((a, b) => a.sort_order - b.sort_order)
        .map((n) => ({
          value: n.value,
          label: n.label,
          color: null,
          is_active: n.is_active,
          sort_order: n.sort_order,
        }))
    }
    const cfgOpts = (fieldDef?.type_config as { options?: { label: string; value: string }[] })?.options
    if (cfgOpts) {
      return coalescePillOptions([], { options: cfgOpts } as Record<string, unknown>)
    }
    return []
  }, [fieldType, fieldDef])

  const displayValue = useMemo(() => {
    if (displayValueOverride) return displayValueOverride
    if (value == null || value === '') return '-'

    if (fieldDef?.type_config?.value_kind === 'actor') {
      return formatActorFieldValue(value)
    }

    if (isUserSelect) {
      if (!userId) return '-'
      if (!selectedUser) return `User #${userId}`
      const secondary = selectedUser.public_id || selectedUser.phone || selectedUser.email
      return secondary ? `${selectedUser.name} · ${secondary}` : selectedUser.name
    }

    if (isEmployeeSelect) {
      if (!entityId) return '-'
      if (!selectedEmployee) return `Employee #${entityId}`
      return selectedEmployee.nickname || selectedEmployee.name || selectedEmployee.username
    }

    if (isGroupSelect) {
      if (!entityId) return '-'
      return selectedGroup?.name ?? `Group #${entityId}`
    }

    if (fieldType === 'file') {
      const files = Array.isArray(value)
        ? value
        : value && typeof value === 'object'
          ? [value as Record<string, unknown>]
          : []
      if (!files.length) return '-'
      return files
        .map((f: Record<string, unknown>) => (f.name as string) || (isZh ? '文件' : 'File'))
        .join('、')
    }

    if (fieldType === 'single_select' || fieldType === 'single_select_tree') {
      const opt = pillOptions.find((o) => o.value === strVal)
      if (opt) return opt.label
      if (fieldType === 'single_select_tree') {
        const n = fieldDef?.tree_nodes?.find((t) => t.value === strVal)
        return n ? n.label : strVal
      }
      return strVal
    }
    if (fieldType === 'multi_select' || fieldType === 'multi_select_tree') {
      const selected = Array.isArray(value)
        ? (value as string[])
        : strVal.split(',').filter(Boolean)
      return (
        selected
          .map((v) => {
            const opt = pillOptions.find((o) => o.value === v)
            if (opt) return opt.label
            const node = fieldDef?.tree_nodes?.find((n) => n.value === v)
            return node ? node.label : v
          })
          .join('、') || '-'
      )
    }
    if (fieldType === 'datetime') {
      return formatDatetimeForDisplay(strVal)
    }
    return strVal
  }, [displayValueOverride, value, fieldType, strVal, pillOptions, fieldDef?.tree_nodes, fieldDef?.type_config, isZh, isUserSelect, selectedUser, userId, isEmployeeSelect, entityId, selectedEmployee, isGroupSelect, selectedGroup])

  const readOnlyPillView = useMemo((): ReactNode | null => {
    if (fieldType === 'file' || fieldType === 'rich_text' || isLongTextField) return null
    if (fieldType === 'single_select') {
      if (strVal === '') return null
      const o = pillOptions.find((x) => x.value === strVal)
      if (!o) return null
      return <FieldOptionPill label={o.label} color={o.color} />
    }
    if (fieldType === 'single_select_tree') {
      if (strVal === '') return null
      const n = fieldDef?.tree_nodes?.find((t) => t.value === strVal)
      if (!n) return null
      return <FieldOptionPill label={n.label} color={null} />
    }
    if (fieldType === 'multi_select') {
      const parts = Array.isArray(value)
        ? (value as string[])
        : strVal.split(',').filter(Boolean)
      if (parts.length === 0) return null
      return (
        <span className="inline-flex flex-wrap gap-1.5">
          {parts.map((p) => {
            const o = pillOptions.find((x) => x.value === p)
            return <FieldOptionPill key={p} label={o?.label ?? p} color={o?.color ?? null} />
          })}
        </span>
      )
    }
    if (fieldType === 'multi_select_tree') {
      const parts = Array.isArray(value)
        ? (value as string[])
        : strVal.split(',').filter(Boolean)
      if (parts.length === 0) return null
      return (
        <span className="inline-flex flex-wrap gap-1.5">
          {parts.map((p) => {
            const n = fieldDef?.tree_nodes?.find((t) => t.value === p)
            return <FieldOptionPill key={p} label={n?.label ?? p} color={null} />
          })}
        </span>
      )
    }
    return null
  }, [fieldType, value, strVal, fieldDef?.tree_nodes, pillOptions, isLongTextField])

  const editorField = useMemo<UnifiedField>(() => (
    fieldDef ?? {
      key: fieldKey,
      id: null,
      domain: 'ticket',
      source: 'system' as const,
      name: label,
      description: null,
      help_text: null,
      field_type: fieldType as FieldType,
      type_config: {},
      applicable_modules: null,
      slot_column: null,
      show_in_workspace: null,
      sort_order: 0,
      status: 'active',
      options: [],
      tree_nodes: [],
      created_at: null,
      updated_at: null,
    }
  ), [fieldDef, fieldKey, label, fieldType])

  const editorTypeConfig = useMemo(() => {
    const base = { ...((fieldDef?.type_config ?? {}) as Record<string, unknown>) }
    if (fieldType === FieldType.EMPLOYEE_SELECT) {
      const groupValue = editValues.assignee_group ?? editValues.assignee_group_id
      if (typeof groupValue === 'number') base.group_id = groupValue
    }
    if (fieldType === FieldType.GROUP_SELECT) {
      const assigneeValue = editValues.assignee ?? editValues.agent_id
      if (typeof assigneeValue === 'number') base.member_id = assigneeValue
    }
    return base
  }, [fieldDef, fieldType, editValues.assignee_group, editValues.assignee_group_id, editValues.assignee, editValues.agent_id])

  const needsDoneButton =
    fieldType === FieldType.RICH_TEXT ||
    fieldType === FieldType.FILE ||
    fieldType === FieldType.SINGLE_SELECT_TREE ||
    fieldType === FieldType.MULTI_SELECT_TREE ||
    fieldType === FieldType.MULTI_SELECT

  const isAutoClose =
    fieldType === FieldType.USER_SELECT ||
    fieldType === FieldType.EMPLOYEE_SELECT ||
    fieldType === FieldType.GROUP_SELECT ||
    fieldType === FieldType.ORGANIZATION_SELECT ||
    fieldType === FieldType.SINGLE_SELECT

  const renderEditInput = () => {
    const handleChange = (v: unknown) => {
      onChange(v)
      if (isAutoClose) onStopEdit()
    }

    const editor = (
      <UnifiedFieldValueEditor
        field={editorField}
        value={value}
        onChange={needsDoneButton ? onChange : handleChange}
        typeConfig={editorTypeConfig}
        placeholder={isZh ? '请选择' : 'Select...'}
        autoFocus
      />
    )

    if (needsDoneButton) {
      return (
        <div className="flex flex-col gap-2">
          {editor}
          <button
            type="button"
            className="self-start text-xs font-medium text-primary hover:underline"
            onClick={onStopEdit}
          >
            {isZh ? '完成' : 'Done'}
          </button>
        </div>
      )
    }

    if (fieldType === FieldType.MULTI_LINE_TEXT) {
      return (
        <textarea
          ref={inputRef as React.RefObject<HTMLTextAreaElement>}
          value={strVal}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onStopEdit}
          rows={3}
          className="w-full min-w-0 resize-y rounded-md border border-ring bg-white px-3 py-2 text-sm text-foreground leading-[1.4] outline-none [overflow-wrap:anywhere]"
        />
      )
    }

    if (fieldType === FieldType.NUMBER) {
      return (
        <input
          ref={inputRef as React.RefObject<HTMLInputElement>}
          type="number"
          value={strVal}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
          onBlur={onStopEdit}
          className="h-9 w-full rounded-md border border-ring bg-white px-3 text-sm text-foreground outline-none"
        />
      )
    }

    if (isAutoClose) return editor

    return (
      <input
        ref={inputRef as React.RefObject<HTMLInputElement>}
        type="text"
        value={strVal}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onStopEdit}
        className="h-9 w-full rounded-md border border-ring bg-white px-3 text-sm text-foreground outline-none"
      />
    )
  }

  const isLabelTop = labelPosition === 'top'

  return (
    <div className={cn('flex flex-col gap-2.5', !isLabelTop && 'flex-row items-start gap-3')}>
      {/* Label */}
      <span
        className={cn(
          'text-xs font-medium text-muted-foreground',
          !isLabelTop && 'w-[80px] shrink-0 pt-2 text-right',
        )}
      >
        {label}
        {isRequired && <span className="ml-0.5 text-destructive">*</span>}
      </span>

      {/* Value / Editor */}
      <div className={cn(!isLabelTop && 'min-w-0 flex-1')}>
        {isEditable && isEditing ? (
          renderEditInput()
        ) : (
          <div
            onClick={isEditable ? onStartEdit : undefined}
            className={cn(
              'min-h-[28px] min-w-0 max-w-full text-sm text-foreground [overflow-wrap:anywhere]',
              isLongTextField && 'leading-[1.4]',
              fieldType === FieldType.RICH_TEXT && 'w-full',
              isEditable && 'cursor-text rounded-md px-0 py-0.5 transition-colors hover:bg-accent',
              !isEditable && 'py-0.5',
            )}
          >
            {readOnlyPillView != null ? (
              readOnlyPillView
            ) : isConversationField && entityId > 0 ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  onOpenSessionDrawer(entityId)
                }}
                className="font-medium text-primary hover:underline"
              >
                {displayValue}
              </button>
            ) : isConversationField && callRecordId ? (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  onOpenCallDrawer(callRecordId)
                }}
                className="font-medium text-primary hover:underline"
              >
                {displayValue}
              </button>
            ) : isUserSelect && userId > 0 ? (
              <Link
                href={`/workspace/users/${selectedUser?.public_id || userId}`}
                onClick={(event) => event.stopPropagation()}
                className="inline-block max-w-full truncate font-medium text-primary hover:underline"
              >
                {displayValue}
              </Link>
            ) : isUserSelect ? (
              displayValue
            ) : isEmployeeSelect || isGroupSelect ? (
              displayValue
            ) : fieldType === FieldType.RICH_TEXT ? (
              <FieldValueDisplay
                fieldType={FieldType.RICH_TEXT}
                value={value}
                typeConfig={(fieldDef?.type_config ?? {}) as Record<string, unknown>}
                className="min-w-0"
              />
            ) : (
              displayValue
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Interaction rule evaluation ──

function evaluateConditions(
  conditions: InteractionRuleCondition[],
  logic: 'and' | 'or',
  formValues: Record<string, unknown>,
): boolean {
  if (!conditions || conditions.length === 0) return false
  const results = conditions.map((cond) => {
    const key = cond.field_key ?? (cond.field_id ? String(cond.field_id) : null)
    if (!key) return false
    return evaluateOperator(formValues[key], cond.operator, cond.value)
  })
  return logic === 'and' ? results.every(Boolean) : results.some(Boolean)
}

function evaluateOperator(current: unknown, operator: string, expected: unknown): boolean {
  const strCurrent = current != null ? String(current) : ''
  const strExpected = expected != null ? String(expected) : ''
  const numCurrent = Number(strCurrent)
  const numExpected = Number(strExpected)
  const canCompareAsNumber = Number.isFinite(numCurrent) && Number.isFinite(numExpected)
  const compare = canCompareAsNumber ? numCurrent - numExpected : strCurrent.localeCompare(strExpected)
  switch (operator) {
    case 'eq': case 'equals': case '=': return strCurrent === strExpected
    case 'ne': case 'not_equals': case '!=': return strCurrent !== strExpected
    case 'contains': case 'like': return strCurrent.toLowerCase().includes(strExpected.toLowerCase())
    case 'not_contains': return !strCurrent.toLowerCase().includes(strExpected.toLowerCase())
    case 'starts_with': return strCurrent.toLowerCase().startsWith(strExpected.toLowerCase())
    case 'ends_with': return strCurrent.toLowerCase().endsWith(strExpected.toLowerCase())
    case 'gt': return compare > 0
    case 'gte': return compare >= 0
    case 'lt': return compare < 0
    case 'lte': return compare <= 0
    case 'is_empty': case 'is_null': return Array.isArray(current) ? current.length === 0 : strCurrent === ''
    case 'is_not_empty': case 'is_not_null': return Array.isArray(current) ? current.length > 0 : strCurrent !== ''
    case 'in': return Array.isArray(expected) ? expected.map(String).includes(strCurrent) : false
    case 'not_in': return Array.isArray(expected) ? !expected.map(String).includes(strCurrent) : false
    default: return false
  }
}
