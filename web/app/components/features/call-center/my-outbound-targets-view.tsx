'use client'

import { useMemo, useState } from 'react'
import { IconPhoneCall } from '@tabler/icons-react'
import { toast } from 'sonner'

import { EmptyState, formatDateTime, TargetStatusBadge } from '@/app/components/features/engagement/outbound-task-ui'
import { FieldValueDisplay, FieldValueEditor } from '@/app/components/features/field-system'
import { useCallCenterRuntime } from '@/context/call-center-runtime'
import {
  OUTBOUND_TARGET_STATUS_LABELS,
  type OutboundTarget,
  type OutboundTargetStatus,
  type OutboundTaskField,
} from '@/models/outbound-task'
import { useMyOutboundTargets, useUpdateMyOutboundTarget } from '@/service/use-outbound-tasks'
import {
  activeOutboundTaskFields,
  isEmptyOutboundFieldValue,
  outboundFieldTreeNodes,
  updateOutboundTargetDraft,
} from './outbound-task-fields'

const statusOptions: Array<{ value: '' | OutboundTargetStatus; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: OUTBOUND_TARGET_STATUS_LABELS.pending },
  { value: 'redial', label: OUTBOUND_TARGET_STATUS_LABELS.redial },
  { value: 'completed', label: OUTBOUND_TARGET_STATUS_LABELS.completed },
]

const targetStatusActions = (Object.entries(OUTBOUND_TARGET_STATUS_LABELS) as Array<[OutboundTargetStatus, string]>)
  .filter(([status]) => status !== 'calling')

export function MyOutboundTargetsView({ onStartCall }: { onStartCall?: () => void }) {
  const [status, setStatus] = useState<'' | OutboundTargetStatus>('')
  const { data, isLoading } = useMyOutboundTargets({ page: 1, per_page: 50, status })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [fieldDrafts, setFieldDrafts] = useState<Record<number, Record<string, unknown>>>({})
  const selectedTarget = useMemo(
    () => data?.items.find((item) => item.id === selectedId) ?? data?.items[0] ?? null,
    [data?.items, selectedId],
  )

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-[340px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-4">
          <h1 className="text-lg font-semibold">我的外呼对象</h1>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as '' | OutboundTargetStatus)}
            className="mt-3 h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
          >
            {statusOptions.map((option) => (
              <option key={option.value || 'all'} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {isLoading ? (
            <p className="p-2 text-sm text-muted-foreground">加载中...</p>
          ) : (data?.items.length ?? 0) === 0 ? (
            <EmptyState title="暂无待处理外呼对象" />
          ) : (
            data?.items.map((target) => (
              <button
                key={target.id}
                type="button"
                onClick={() => setSelectedId(target.id)}
                className={`mb-2 w-full rounded-lg border p-3 text-left text-sm transition-colors ${selectedTarget?.id === target.id ? 'border-primary bg-muted/60' : 'border-border hover:bg-muted/40'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{target.phone_number}</span>
                  <TargetStatusBadge status={target.status} />
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">{target.task?.name ?? '外呼任务'}</p>
                <p className="mt-1 text-xs text-muted-foreground">下次跟进：{formatDateTime(target.next_follow_up_at)}</p>
              </button>
            ))
          )}
        </div>
      </aside>
      <main className="min-h-0 flex-1 overflow-auto bg-background p-6">
        {selectedTarget ? (
          <TargetExecutionPanel
            key={selectedTarget.id}
            target={selectedTarget}
            fieldValues={fieldDrafts[selectedTarget.id] ?? selectedTarget.field_values ?? {}}
            hasFieldDraft={fieldDrafts[selectedTarget.id] !== undefined}
            onFieldChange={(fieldKey, value) => {
              setFieldDrafts((current) => updateOutboundTargetDraft(
                current,
                selectedTarget.id,
                selectedTarget.field_values ?? {},
                fieldKey,
                value,
              ))
            }}
            onFieldsSaved={() => {
              setFieldDrafts((current) => {
                const next = { ...current }
                delete next[selectedTarget.id]
                return next
              })
            }}
            onStartCall={onStartCall}
          />
        ) : (
          <EmptyState title="请选择外呼对象" />
        )}
      </main>
    </div>
  )
}

function TargetExecutionPanel({
  target,
  fieldValues,
  hasFieldDraft,
  onFieldChange,
  onFieldsSaved,
  onStartCall,
}: {
  target: OutboundTarget
  fieldValues: Record<string, unknown>
  hasFieldDraft: boolean
  onFieldChange: (fieldKey: string, value: unknown) => void
  onFieldsSaved: () => void
  onStartCall?: () => void
}) {
  const { setDraftDialNumber } = useCallCenterRuntime()
  const updateTarget = useUpdateMyOutboundTarget()
  const [currentStatus, setCurrentStatus] = useState(target.status)
  const [pendingStatus, setPendingStatus] = useState<OutboundTargetStatus | null>(null)
  const [savingFields, setSavingFields] = useState(false)
  const taskFields = useMemo(() => activeOutboundTaskFields(target.task?.fields), [target.task?.fields])
  const editableFields = useMemo(() => taskFields.filter((field) => field.agent_editable), [taskFields])

  const startCall = () => {
    setDraftDialNumber(target.phone_number)
    onStartCall?.()
    toast.success('号码已填入呼叫栏')
  }

  const updateStatus = async (status: Exclude<OutboundTargetStatus, 'calling'>) => {
    if (status === currentStatus || pendingStatus) return
    setPendingStatus(status)
    try {
      await updateTarget.mutateAsync({
        targetId: target.id,
        data: { status },
      })
      setCurrentStatus(status)
      toast.success(`外呼对象状态已更新为${OUTBOUND_TARGET_STATUS_LABELS[status]}`)
    } catch {
      toast.error('外呼对象状态更新失败，请重试')
    } finally {
      setPendingStatus(null)
    }
  }

  const saveFields = async () => {
    const missingField = taskFields.find(
      (field) => field.required && isEmptyOutboundFieldValue(fieldValues[field.key]),
    )
    if (missingField) {
      toast.error(`请填写必填字段：${missingField.name}`)
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
      toast.success('业务记录已保存')
    } catch {
      toast.error('业务记录保存失败，请重试')
    } finally {
      setSavingFields(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="rounded-lg border border-border p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">呼叫号码</p>
            <h2 className="mt-1 text-2xl font-semibold">{target.phone_number}</h2>
          </div>
          <button
            type="button"
            onClick={startCall}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            <IconPhoneCall size={17} />
            呼叫
          </button>
        </div>
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-3">
          <Info label="任务" value={target.task?.name ?? '-'} />
          <Info label="状态" value={OUTBOUND_TARGET_STATUS_LABELS[target.status]} />
          <Info label="最近结果" value={target.last_call_result || '-'} />
        </div>
      </section>

      <section className="rounded-lg border border-border p-5">
        <h3 className="mb-4 text-base font-semibold">外呼对象状态</h3>
        <div className="flex flex-wrap gap-2">
          {targetStatusActions.map(([status, label]) => {
            const active = currentStatus === status
            const saving = pendingStatus === status
            return (
              <button
                key={status}
                type="button"
                onClick={() => void updateStatus(status as Exclude<OutboundTargetStatus, 'calling'>)}
                disabled={pendingStatus !== null}
                className={`rounded-md border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-60 ${
                  active
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-background hover:bg-muted'
                }`}
              >
                {saving ? '更新中...' : label}
              </button>
            )
          })}
        </div>
      </section>

      <section className="rounded-lg border border-border p-5">
        <h3 className="mb-4 text-base font-semibold">业务记录</h3>
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
          <p className="text-sm text-muted-foreground">暂无业务记录字段</p>
        )}
        {editableFields.length > 0 && (
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => void saveFields()}
              disabled={!hasFieldDraft || savingFields}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {savingFields ? '保存中...' : '保存业务记录'}
            </button>
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

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted/50 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  )
}
