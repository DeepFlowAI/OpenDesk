'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { FieldValueDisplay, FieldValueEditor } from '@/app/components/features/field-system'
import {
  activeOutboundTaskFields,
  outboundFieldTreeNodes,
} from '@/app/components/features/call-center/outbound-task-fields'
import { autoOutboundTaskId } from '@/lib/auto-outbound-incoming'
import { useLocaleStore } from '@/context/locale-store'
import type { IncomingCall } from '@/lib/call-session-reducer'
import type { OutboundTaskField } from '@/models/outbound-task'
import {
  useAutoOutboundAgentContext,
  useSubmitAutoOutboundWrapup,
} from '@/service/use-auto-outbound-tasks'
import { t } from '@/utils/i18n'

type Props = {
  incoming: IncomingCall | null
  phase: 'on_call' | 'wrap_up' | string
  callRecordId?: number | null
  onSubmitted: () => void
}

export function AutoOutboundBusinessPanel({
  incoming,
  phase,
  callRecordId,
  onSubmitted,
}: Props) {
  const { locale } = useLocaleStore()
  const taskId = autoOutboundTaskId(incoming) ?? 0
  const phoneNumber = incoming?.to || incoming?.customer_from || incoming?.from || null
  const contextQuery = useAutoOutboundAgentContext(
    taskId,
    { call_record_id: callRecordId, phone_number: phoneNumber },
    taskId > 0,
  )
  const submitWrapup = useSubmitAutoOutboundWrapup()

  const [fieldValues, setFieldValues] = useState<Record<string, unknown>>({})
  const submittedRef = useRef(false)

  // Prefer push record_id; fall back to agent-context resolution.
  const recordId = useMemo(() => {
    const fromPush = Number(incoming?.record_id)
    if (Number.isFinite(fromPush) && fromPush > 0) return fromPush
    const fromCtx = Number(contextQuery.data?.record?.id)
    if (Number.isFinite(fromCtx) && fromCtx > 0) return fromCtx
    return null
  }, [incoming?.record_id, contextQuery.data?.record?.id])

  const taskFields = useMemo(
    () => activeOutboundTaskFields(contextQuery.data?.fields),
    [contextQuery.data?.fields],
  )

  // Seed drafts once when agent-context first resolves (keep in-call edits).
  useEffect(() => {
    if (!contextQuery.data) return
    const fromRecord = contextQuery.data.record?.field_values
    const seeded =
      fromRecord && typeof fromRecord === 'object' && !Array.isArray(fromRecord)
        ? { ...fromRecord }
        : {}
    setFieldValues((prev) => (Object.keys(prev).length > 0 ? prev : seeded))
  }, [contextQuery.data])

  const submit = async () => {
    if (submittedRef.current || submitWrapup.isPending) return
    if (!taskId || !recordId) {
      toast.error(t('ws.autoOutbound.agent.missingRecord', locale))
      return
    }
    submittedRef.current = true
    try {
      await submitWrapup.mutateAsync({
        taskId,
        recordId,
        data: {
          field_values: fieldValues,
          reception_result: { field_values: fieldValues },
        },
      })
      toast.success(t('ws.autoOutbound.agent.wrapupSaved', locale))
      if (phase === 'wrap_up') onSubmitted()
    } catch {
      toast.error(t('ws.autoOutbound.agent.wrapupFailed', locale))
    } finally {
      submittedRef.current = false
    }
  }

  const submitLabel =
    phase === 'on_call'
      ? t('ws.autoOutbound.agent.saveRecord', locale)
      : phase === 'wrap_up'
        ? t('ws.autoOutbound.agent.submitContinue', locale)
        : t('ws.autoOutbound.agent.saveChanges', locale)

  if (contextQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">{t('ws.autoOutbound.loading', locale)}</p>
  }

  if (contextQuery.isError || !contextQuery.data) {
    return (
      <p className="text-sm text-muted-foreground">
        {t('ws.autoOutbound.agent.contextLoadFailed', locale)}
      </p>
    )
  }

  const ctx = contextQuery.data

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-muted/50 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
        {t('ws.autoOutbound.agent.summary', locale, {
          taskName: ctx.task_name,
          templateName: ctx.template_name || '—',
        })}
        {phase !== 'wrap_up' && (
          <span className="mt-1 block">{t('ws.autoOutbound.agent.prefillHint', locale)}</span>
        )}
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold text-foreground">
          {t('ws.autoOutbound.agent.fieldsTitle', locale)}
        </div>
        <p className="mb-3 text-[11px] text-muted-foreground">
          {t('ws.autoOutbound.agent.fieldsHint', locale)}
        </p>
        {taskFields.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('ws.autoOutbound.agent.noFields', locale)}</p>
        ) : (
          <div className="space-y-3">
            {taskFields.map((field) => (
              <BusinessFieldRow
                key={field.key}
                field={field}
                value={fieldValues[field.key]}
                onChange={(value) =>
                  setFieldValues((current) => ({ ...current, [field.key]: value }))
                }
              />
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        disabled={submitWrapup.isPending || !recordId}
        onClick={() => void submit()}
        className="h-10 w-full rounded-lg bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60"
      >
        {submitWrapup.isPending
          ? t('ws.autoOutbound.agent.submitting', locale)
          : submitLabel}
      </button>
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
    <div>
      <div className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground">
        <span>{field.name}</span>
        {field.required && <span className="text-destructive">*</span>}
      </div>
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
        <div className="min-w-0 text-sm text-foreground">
          <FieldValueDisplay
            fieldType={field.field_type}
            value={value}
            typeConfig={field.type_config}
            treeNodes={outboundFieldTreeNodes(field)}
          />
        </div>
      )}
    </div>
  )
}
