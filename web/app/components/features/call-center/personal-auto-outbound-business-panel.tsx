'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { FieldValueDisplay, FieldValueEditor } from '@/app/components/features/field-system'
import { activeOutboundTaskFields, outboundFieldTreeNodes } from '@/app/components/features/call-center/outbound-task-fields'
import { useLocaleStore } from '@/context/locale-store'
import type { IncomingCall } from '@/lib/call-session-reducer'
import type { OutboundTaskField } from '@/models/outbound-task'
import { usePersonalAutoOutboundBusinessContext, useSubmitPersonalAutoOutboundWrapup } from '@/service/use-personal-auto-outbound'
import { t } from '@/utils/i18n'

export function PersonalAutoOutboundBusinessPanel({
  incoming,
  onSubmitted,
}: {
  incoming: IncomingCall | null
  onSubmitted: () => void
}) {
  const { locale } = useLocaleStore()
  const callId = Number(incoming?.record_id || 0)
  const contextQuery = usePersonalAutoOutboundBusinessContext(callId, callId > 0)
  const submitWrapup = useSubmitPersonalAutoOutboundWrapup()
  const [fieldValues, setFieldValues] = useState<Record<string, unknown>>({})
  const submittedRef = useRef(false)

  const taskFields = useMemo(
    () => activeOutboundTaskFields(contextQuery.data?.fields),
    [contextQuery.data?.fields],
  )

  useEffect(() => {
    const values = contextQuery.data?.record?.field_values
    if (!values) return
    setFieldValues((current) => (Object.keys(current).length > 0 ? current : { ...values }))
  }, [contextQuery.data?.record?.field_values])

  const submit = async () => {
    if (!callId || submittedRef.current || submitWrapup.isPending) return
    submittedRef.current = true
    try {
      await submitWrapup.mutateAsync({
        callId,
        data: {
          field_values: fieldValues,
          reception_result: { field_values: fieldValues },
        },
      })
      toast.success(t('personalAuto.wrapupSaved', locale))
      onSubmitted()
    } catch {
      submittedRef.current = false
      toast.error(t('personalAuto.wrapupFailed', locale))
    }
  }

  if (contextQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">{t('ws.autoOutbound.loading', locale)}</p>
  }
  if (contextQuery.isError || !contextQuery.data) {
    return <p className="text-sm text-muted-foreground">{t('personalAuto.contextLoadFailed', locale)}</p>
  }

  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-muted/50 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
        {t('personalAuto.businessSummary', locale, {
          taskName: contextQuery.data.task_name,
        })}
        {incoming?.personal_assignment_type === 'fallback' && <span className="mt-1 block text-amber-700">{t('personalAuto.fallbackHandoffHint', locale)}</span>}
      </div>
      <div>
        <div className="mb-2 text-xs font-semibold text-foreground">{t('ws.autoOutbound.agent.fieldsTitle', locale)}</div>
        <p className="mb-3 text-[11px] text-muted-foreground">{t('personalAuto.fieldsHint', locale)}</p>
        {taskFields.length === 0 ? <p className="text-sm text-muted-foreground">{t('ws.autoOutbound.agent.noFields', locale)}</p> : <div className="space-y-3">{taskFields.map((field) => <BusinessFieldRow key={field.key} field={field} value={fieldValues[field.key]} onChange={(value) => setFieldValues((current) => ({ ...current, [field.key]: value }))} />)}</div>}
      </div>
      <button type="button" disabled={submitWrapup.isPending} onClick={() => void submit()} className="h-10 w-full rounded-lg bg-primary text-sm font-medium text-primary-foreground disabled:opacity-60">{submitWrapup.isPending ? t('ws.autoOutbound.agent.submitting', locale) : t('ws.autoOutbound.agent.submitContinue', locale)}</button>
    </div>
  )
}

function BusinessFieldRow({ field, value, onChange }: { field: OutboundTaskField; value: unknown; onChange: (value: unknown) => void }) {
  return <div><div className="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted-foreground"><span>{field.name}</span>{field.required && <span className="text-destructive">*</span>}</div>{field.agent_editable ? <FieldValueEditor fieldType={field.field_type} value={value} onChange={onChange} typeConfig={field.type_config} treeNodes={outboundFieldTreeNodes(field)} className="min-w-0" /> : <div className="rounded-md border border-border px-3 py-2 text-sm"><FieldValueDisplay fieldType={field.field_type} value={value} typeConfig={field.type_config} treeNodes={outboundFieldTreeNodes(field)} /></div>}</div>
}
