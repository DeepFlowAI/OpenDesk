'use client'

import { useMemo, useState } from 'react'
import { IconLayoutColumns, IconPhone, IconSitemap, IconUser } from '@tabler/icons-react'
import { toast } from 'sonner'

import { formatDateTime } from '@/app/components/features/engagement/outbound-task-ui'
import { FieldValueDisplay, FieldValueEditor } from '@/app/components/features/field-system'
import { useCallCenterRuntime } from '@/context/call-center-runtime'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type {
  OutboundTarget,
  OutboundTaskField,
  OutboundTaskStatus,
} from '@/models/outbound-task'
import { useMyOutboundTargetRecords, useUpdateMyOutboundTarget } from '@/service/use-outbound-tasks'
import { t } from '@/utils/i18n'
import { ExecTargetStatusBadge } from './my-outbound-badges'
import { MyOutboundCallRecords } from './my-outbound-call-records'
import {
  activeOutboundTaskFields,
  isEmptyOutboundFieldValue,
  outboundFieldTreeNodes,
} from './outbound-task-fields'

const CALL_BLOCKED_TARGET_STATUSES = new Set(['completed', 'do_not_call', 'invalid_number'])

export function MyOutboundTargetPanel({
  target,
  taskStatus,
  fieldValues,
  hasFieldDraft,
  onFieldChange,
  onFieldsSaved,
  onStartCall,
  onOpenScript,
  onOpenScreenPop,
}: {
  target: OutboundTarget
  taskStatus: OutboundTaskStatus
  fieldValues: Record<string, unknown>
  hasFieldDraft: boolean
  onFieldChange: (fieldKey: string, value: unknown) => void
  onFieldsSaved: () => void
  onStartCall?: (phone: string, taskId: number) => void | Promise<void>
  onOpenScript: () => void
  onOpenScreenPop?: (target: OutboundTarget) => void
}) {
  const { locale } = useLocaleStore()
  const { setDraftDialNumber } = useCallCenterRuntime()
  const updateTarget = useUpdateMyOutboundTarget()
  const [activeTab, setActiveTab] = useState<'business' | 'records'>('business')
  const [savingFields, setSavingFields] = useState(false)
  const [placingCall, setPlacingCall] = useState(false)
  const taskFields = useMemo(() => activeOutboundTaskFields(target.task?.fields), [target.task?.fields])
  const editableFields = useMemo(() => taskFields.filter((field) => field.agent_editable), [taskFields])
  const recordsQuery = useMyOutboundTargetRecords(target.id, activeTab === 'records')

  const callDisabledReason =
    taskStatus !== 'active'
      ? t('ws.outboundExec.panel.callDisabledTask', locale)
      : CALL_BLOCKED_TARGET_STATUSES.has(target.status)
        ? t('ws.outboundExec.panel.callDisabledTarget', locale)
        : null

  const startCall = async () => {
    if (placingCall || callDisabledReason) return
    setDraftDialNumber(target.phone_number)
    setPlacingCall(true)
    try {
      await onStartCall?.(target.phone_number, target.task_id)
    } finally {
      setPlacingCall(false)
    }
  }

  const saveFields = async () => {
    const missingField = taskFields.find(
      (field) => field.required && isEmptyOutboundFieldValue(fieldValues[field.key]),
    )
    if (missingField) {
      toast.error(t('ws.outboundExec.business.requiredMissing', locale, { name: missingField.name }))
      return
    }

    setSavingFields(true)
    try {
      await updateTarget.mutateAsync({
        targetId: target.id,
        data: {
          field_values: Object.fromEntries(
            editableFields.map((field) => [field.key, fieldValues[field.key] ?? null]),
          ),
        },
      })
      onFieldsSaved()
      toast.success(t('ws.outboundExec.business.saved', locale))
    } catch {
      toast.error(t('ws.outboundExec.business.saveFailed', locale))
    } finally {
      setSavingFields(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-lg font-semibold">{target.user_name || target.phone_number}</h2>
              <ExecTargetStatusBadge status={target.status} />
            </div>
            <p className="mt-1 font-mono text-xl font-semibold tracking-wide">{target.phone_number}</p>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
              <IconUser size={13} />
              {target.user_name
                ? t('ws.outboundExec.panel.linkedUser', locale, { name: target.user_name })
                : t('ws.outboundExec.panel.noLinkedUser', locale)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {onOpenScreenPop && (
              <button
                type="button"
                onClick={() => onOpenScreenPop(target)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
              >
                <IconLayoutColumns size={15} />
                {t('ws.outboundExec.panel.screenPop', locale)}
              </button>
            )}
            {target.task?.has_script && (
              <button
                type="button"
                onClick={onOpenScript}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-sm font-medium hover:bg-muted"
              >
                <IconSitemap size={15} />
                {t('ws.outboundExec.panel.script', locale)}
              </button>
            )}
            <button
              type="button"
              onClick={() => void startCall()}
              disabled={placingCall || callDisabledReason !== null}
              title={callDisabledReason ?? undefined}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm disabled:opacity-60"
            >
              <IconPhone size={15} />
              {placingCall ? t('ws.outboundExec.panel.calling', locale) : t('ws.outboundExec.panel.call', locale)}
            </button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
          <InfoItem label={t('ws.outboundExec.panel.info.task', locale)} value={target.task?.name ?? '-'} />
          <InfoItem label={t('ws.outboundExec.panel.info.lastResult', locale)} value={target.last_call_result || '—'} />
          <InfoItem label={t('ws.outboundExec.panel.info.nextFollowUp', locale)} value={formatDateTime(target.next_follow_up_at)} />
          <InfoItem
            label={t('ws.outboundExec.panel.info.callCount', locale)}
            value={t('ws.outboundExec.panel.callCountValue', locale, { count: target.call_count })}
          />
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b border-border pr-5">
          <div className="flex items-center gap-1 px-3 pt-2.5">
            {(['business', 'records'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'px-3 pb-2 text-sm transition-colors',
                  activeTab === tab
                    ? 'border-b-2 border-primary font-medium text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t(tab === 'business' ? 'ws.outboundExec.tab.business' : 'ws.outboundExec.tab.records', locale)}
              </button>
            ))}
          </div>
          {activeTab === 'records' && recordsQuery.data && (
            <span className="text-xs text-muted-foreground">
              {t('ws.outboundExec.records.total', locale, { count: recordsQuery.data.items.length })}
            </span>
          )}
        </div>
        {activeTab === 'business' ? (
          <div className="p-5">
            {taskFields.length > 0 ? (
              <div className="divide-y divide-border rounded-md border border-border">
                {taskFields.map((field) => (
                  <BusinessFieldRow
                    key={`${target.id}-${field.key}`}
                    field={field}
                    value={fieldValues[field.key]}
                    onChange={(value) => onFieldChange(field.key, value)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('ws.outboundExec.business.empty', locale)}</p>
            )}
            {editableFields.length > 0 && (
              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  onClick={() => void saveFields()}
                  disabled={!hasFieldDraft || savingFields}
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
                >
                  {savingFields ? t('ws.outboundExec.business.saving', locale) : t('ws.outboundExec.business.save', locale)}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="p-5">
            <MyOutboundCallRecords recordsQuery={recordsQuery} />
          </div>
        )}
      </section>
    </div>
  )
}

function BusinessFieldRow({
  field,
  value,
  onChange,
}: {
  field: OutboundTaskField
  value: unknown
  onChange: (value: unknown) => void
}) {
  return (
    <div className="grid gap-2 px-4 py-3 text-sm md:grid-cols-[180px_minmax(0,1fr)] md:items-center">
      <div className="flex items-center gap-1 font-medium">
        <span>{field.name}</span>
        {field.required && <span className="text-destructive">*</span>}
      </div>
      <div className="min-w-0">
        {field.agent_editable ? (
          <FieldValueEditor
            fieldType={field.field_type}
            value={value}
            onChange={onChange}
            typeConfig={field.type_config}
            treeNodes={outboundFieldTreeNodes(field)}
            className="min-w-0"
          />
        ) : (
          <FieldValueDisplay
            fieldType={field.field_type}
            value={value}
            typeConfig={field.type_config}
            treeNodes={outboundFieldTreeNodes(field)}
          />
        )}
      </div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 truncate text-xs font-medium">{value}</div>
    </div>
  )
}
