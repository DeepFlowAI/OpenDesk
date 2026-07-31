'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconPlus, IconTrash, IconChevronDown } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type {
  RoutingCondition,
  RoutingConditionType,
  RoutingTargetType,
} from '@/models/inbound-routing-rule'
import type { AssignQueueTarget, AssignQueueTargetType } from '@/models/voice-flow-graph'
import { useServiceHours } from '@/service/use-service-hours'
import { useVoiceFlowsSelect } from '@/service/use-voice-flows'
import { useEmployeeGroups, useEmployeeSelect } from '@/service/use-employee-groups'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { FieldDomain, FieldType } from '@/types/field-enums'
import {
  useInboundRoutingRule,
  useCreateInboundRoutingRule,
  useUpdateInboundRoutingRule,
} from '@/service/use-inbound-routing-rules'
import { useTenantPhoneNumbers } from '@/service/use-tenant-phone-numbers'
import {
  VoiceSpeedAgentSelect,
  isVoiceSpeedSelectBlocking,
  type VoiceSpeedAgentSelectStatus,
} from '@/app/components/features/voice-speed-agent-select'

type RowState = RoutingCondition & { _key: string }

function newKey() {
  return `k-${Math.random().toString(36).slice(2, 11)}`
}

function defaultRow(): RowState {
  return { _key: newKey(), condition_type: 'caller_number', operator: 'eq', value: '' }
}

function normalizeOperators(ct: RoutingConditionType): string[] {
  if (ct === 'call_time') return ['in_schedule', 'not_in_schedule']
  return ['eq', 'ne', 'contains', 'not_contains']
}

function opLabel(op: string, locale: import('@/context/locale-store').Locale): string {
  if (op === 'eq') return t('rr.cond.op.eq', locale)
  if (op === 'ne') return t('rr.cond.op.ne', locale)
  if (op === 'contains') return t('rr.cond.op.contains', locale)
  if (op === 'not_contains') return t('rr.cond.op.notContains', locale)
  if (op === 'in_schedule') return t('rr.cond.op.in', locale)
  if (op === 'not_in_schedule') return t('rr.cond.op.notIn', locale)
  return op
}

type RoutingRuleFormProps = { ruleId?: number }

export function RoutingRuleForm({ ruleId }: RoutingRuleFormProps) {
  const isNew = ruleId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: rule, isLoading: loadingRule } = useInboundRoutingRule(ruleId ?? 0)
  const { data: flows } = useVoiceFlowsSelect()
  const { data: serviceHoursList } = useServiceHours()
  const { data: phoneNumbers } = useTenantPhoneNumbers({ page: 1, per_page: 200 })
  const createMut = useCreateInboundRoutingRule()
  const updateMut = useUpdateInboundRoutingRule()
  const phoneOptions = useMemo(
    () => (phoneNumbers?.items ?? []).map((p) => p.phone_number).filter(Boolean),
    [phoneNumbers?.items],
  )

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [targetType, setTargetType] = useState<RoutingTargetType>('voice_flow')
  // Each target type keeps its own temp values so switching back and forth
  // doesn't lose what the user already filled in. Only the active type is
  // submitted on save.
  const [targetFlowId, setTargetFlowId] = useState<number | ''>('')
  const [vsAgentId, setVsAgentId] = useState('')
  const [vsAgentName, setVsAgentName] = useState('')
  const [transferTarget, setTransferTarget] = useState<AssignQueueTarget>({
    queue_type: 'employee_group',
    queue_id: null,
  })
  const [vsStatus, setVsStatus] = useState<VoiceSpeedAgentSelectStatus>('loading')
  const [rows, setRows] = useState<RowState[]>([])
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (isNew) {
      if (!initialized) {
        setRows([])
        setInitialized(true)
      }
      return
    }
    if (!rule || initialized) return
    setName(rule.name)
    setEnabled(rule.enabled)
    setTargetType(rule.target_type ?? 'voice_flow')
    setTargetFlowId(rule.target_voice_flow_id ?? '')
    setVsAgentId(rule.voicespeed_agent_id ?? '')
    setVsAgentName(rule.voicespeed_agent_name ?? '')
    if (rule.transfer_target) setTransferTarget(rule.transfer_target)
    setRows((rule.conditions ?? []).map((c) => ({ ...c, _key: newKey() })))
    setInitialized(true)
  }, [isNew, rule, initialized])

  const [savedSnapshot, setSavedSnapshot] = useState('')
  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false)
  useEffect(() => {
    if (isNew) {
      setSavedSnapshot('')
      return
    }
    if (rule && initialized) {
      const savedTarget =
        rule.target_type === 'voicespeed_agent'
          ? {
              type: 'voicespeed_agent',
              agent: rule.voicespeed_agent_id ?? '',
              transfer: rule.transfer_target ?? null,
            }
          : { type: 'voice_flow', flow: rule.target_voice_flow_id ?? '' }
      setSavedSnapshot(
        JSON.stringify({
          name: rule.name.trim(),
          enabled: rule.enabled,
          target: savedTarget,
          conditions: rule.conditions ?? [],
        })
      )
    }
  }, [isNew, rule, initialized])

  const payloadForCompare = useMemo(() => {
    const target =
      targetType === 'voicespeed_agent'
        ? { type: 'voicespeed_agent', agent: vsAgentId, transfer: vsAgentId ? transferTarget : null }
        : { type: 'voice_flow', flow: targetFlowId === '' ? '' : Number(targetFlowId) }
    return JSON.stringify({
      name: name.trim(),
      enabled,
      target,
      conditions: rows.map(({ _key: _, ...c }) => c),
    })
  }, [name, enabled, targetType, targetFlowId, vsAgentId, transferTarget, rows])

  const emptyNewSnapshot = JSON.stringify({
    name: '',
    enabled: true,
    target: { type: 'voice_flow', flow: '' },
    conditions: [],
  })
  const isDirty = isNew ? payloadForCompare !== emptyNewSnapshot : payloadForCompare !== savedSnapshot

  const goBack = () => {
    if (isDirty) {
      setLeaveConfirmOpen(true)
      return
    }
    router.push('/flow-studio/routing-rules')
  }

  const addRow = () => setRows((r) => [...r, defaultRow()])
  const removeRow = (key: string) => setRows((r) => r.filter((x) => x._key !== key))

  const updateRow = useCallback((key: string, patch: Partial<RowState>) => {
    setRows((r) =>
      r.map((row) => {
        if (row._key !== key) return row
        const next = { ...row, ...patch }
        if (patch.condition_type) {
          const ops = normalizeOperators(patch.condition_type)
          if (!ops.includes(next.operator)) next.operator = ops[0]
        }
        return next
      })
    )
  }, [])

  const handleSave = async () => {
    const tn = name.trim()
    if (!tn || tn.length > 64) {
      toast.error(t('rr.form.validation.name', locale))
      return
    }
    const conditions: RoutingCondition[] = rows.map(({ _key: _, ...c }) => c)

    let body: import('@/models/inbound-routing-rule').SaveInboundRoutingRulePayload
    if (targetType === 'voice_flow') {
      if (targetFlowId === '') {
        toast.error(t('rr.form.validation.flow', locale))
        return
      }
      body = {
        name: tn,
        enabled,
        conditions,
        target_type: 'voice_flow',
        target_voice_flow_id: Number(targetFlowId),
      }
    } else {
      if (isVoiceSpeedSelectBlocking(vsStatus)) {
        toast.error(t('vs.agent.toast.unavailable', locale))
        return
      }
      if (!vsAgentId) {
        toast.error(t('rr.form.validation.agent', locale))
        return
      }
      if (transferTarget.queue_id == null) {
        toast.error(t('rr.form.validation.transfer', locale))
        return
      }
      body = {
        name: tn,
        enabled,
        conditions,
        target_type: 'voicespeed_agent',
        voicespeed_agent_id: vsAgentId,
        voicespeed_agent_name: vsAgentName,
        transfer_target: transferTarget,
      }
    }

    try {
      if (isNew) {
        await createMut.mutateAsync(body)
        toast.success(t('rr.form.saveSuccess', locale))
        router.push('/flow-studio/routing-rules')
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: body })
        toast.success(t('rr.form.saveSuccess', locale))
        setSavedSnapshot(payloadForCompare)
      }
    } catch {
      toast.error(t('rr.form.saveFailed', locale))
    }
  }

  const targetIncomplete =
    targetType === 'voice_flow'
      ? targetFlowId === ''
      : !vsAgentId || transferTarget.queue_id == null || isVoiceSpeedSelectBlocking(vsStatus)
  const saveDisabled =
    createMut.isPending || updateMut.isPending || !isDirty || !name.trim() || targetIncomplete

  if (!isNew && loadingRule) {
    return <p className="p-8 text-sm text-muted-foreground">{t('rr.loading', locale)}</p>
  }
  if (!isNew && !rule && !loadingRule) {
    return <p className="p-8 text-sm text-red-600">Not found</p>
  }

  const title = isNew
    ? t('rr.form.newTitle', locale)
    : t('rr.form.editTitle', locale, { name: rule?.name ?? '' })

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar — design: h-56, px-24, border-bottom */}
      <div className="sticky -top-8 z-20 flex h-14 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={goBack}
          className="flex items-center gap-2 text-left transition-colors"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="button"
          disabled={saveDisabled}
          onClick={handleSave}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-40"
        >
          {createMut.isPending || updateMut.isPending
            ? t('rr.form.saving', locale)
            : t('rr.form.save', locale)}
        </button>
      </div>

      {/* Form content — design: padding 32, gap 20 */}
      <div className="flex flex-col gap-5 p-8">
        {/* Rule name */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground/80">{t('rr.form.name', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('rr.form.name.placeholder', locale)}
            className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* Enabled toggle — design: 24h x 44w, cornerRadius 12, knob 20px */}
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground/80">{t('rr.form.enabled', locale)}</span>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>

        {/* Conditions section */}
        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium text-foreground/80">{t('rr.form.conditions', locale)}</span>
          <p className="text-[13px] text-muted-foreground">{t('rr.form.conditions.hint', locale)}</p>

          {/* Condition list — design: cornerRadius 8, border #E5E5E5, rows h-48 px-16 gap-8 */}
          {rows.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border">
              {rows.map((row, idx) => (
                <div
                  key={row._key}
                  className={cn(
                    'flex h-12 items-center gap-2 px-4',
                    idx < rows.length - 1 && 'border-b border-border'
                  )}
                >
                  {/* Condition type dropdown */}
                  <div className="relative w-[120px] shrink-0">
                    <select
                      value={row.condition_type}
                      onChange={(e) =>
                        updateRow(row._key, { condition_type: e.target.value as RoutingConditionType })
                      }
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="caller_number">{t('rr.cond.type.caller', locale)}</option>
                      <option value="callee_number">{t('rr.cond.type.callee', locale)}</option>
                      <option value="call_time">{t('rr.cond.type.time', locale)}</option>
                    </select>
                    <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  </div>

                  {/* Operator dropdown */}
                  <div className="relative w-[110px] shrink-0">
                    <select
                      value={row.operator}
                      onChange={(e) => updateRow(row._key, { operator: e.target.value })}
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      {normalizeOperators(row.condition_type).map((op) => (
                        <option key={op} value={op}>
                          {opLabel(op, locale)}
                        </option>
                      ))}
                    </select>
                    <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  </div>

                  {/* Value input/select */}
                  {row.condition_type === 'call_time' ? (
                    <div className="relative min-w-0 flex-1">
                      <select
                        value={row.value}
                        onChange={(e) => updateRow(row._key, { value: e.target.value })}
                        className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        <option value="">{t('rr.cond.value.schedule.placeholder', locale)}</option>
                        {(serviceHoursList ?? []).map((sh) => (
                          <option key={sh.id} value={String(sh.id)}>
                            {sh.name}
                          </option>
                        ))}
                      </select>
                      <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    </div>
                  ) : row.condition_type === 'callee_number' ? (
                    <div className="relative min-w-0 flex-1">
                      <select
                        value={row.value}
                        onChange={(e) => updateRow(row._key, { value: e.target.value })}
                        className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        <option value="">{t('rr.cond.value.phonePool.placeholder', locale)}</option>
                        {row.value && !phoneOptions.includes(row.value) && (
                          <option value={row.value}>{row.value}</option>
                        )}
                        {phoneOptions.map((num) => (
                          <option key={num} value={num}>
                            {num}
                          </option>
                        ))}
                      </select>
                      <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    </div>
                  ) : (
                    <input
                      value={row.value}
                      onChange={(e) => updateRow(row._key, { value: e.target.value })}
                      placeholder={t('rr.cond.value.phone.placeholder', locale)}
                      className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-white px-2.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  )}

                  {/* Delete icon — design: trash-2 16px #737373 */}
                  <button
                    type="button"
                    onClick={() => removeRow(row._key)}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-red-600"
                    aria-label="delete condition"
                  >
                    <IconTrash size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add condition button — design: cornerRadius 8, h-36, px-14, border #E5E5E5, gap 6 */}
          <button
            type="button"
            onClick={addRow}
            className="inline-flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconPlus size={16} />
            {t('rr.form.addCondition', locale)}
          </button>
        </div>

        {/* Target — voice flow or VoiceSpeed agent */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground/80">{t('rr.form.target', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>

          {/* Target type segmented control */}
          <div className="inline-flex w-fit rounded-lg border border-border p-0.5">
            {(['voice_flow', 'voicespeed_agent'] as RoutingTargetType[]).map((tt) => (
              <button
                key={tt}
                type="button"
                onClick={() => setTargetType(tt)}
                className={cn(
                  'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
                  targetType === tt
                    ? 'bg-primary text-white'
                    : 'text-foreground/70 hover:bg-accent'
                )}
              >
                {tt === 'voice_flow'
                  ? t('rr.form.target.voiceFlow', locale)
                  : t('rr.form.target.voiceSpeed', locale)}
              </button>
            ))}
          </div>

          {targetType === 'voice_flow' ? (
            <div className="relative">
              <select
                value={targetFlowId === '' ? '' : String(targetFlowId)}
                onChange={(e) => setTargetFlowId(e.target.value ? Number(e.target.value) : '')}
                className="h-10 w-full appearance-none rounded-lg border border-border bg-white px-3 pr-9 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="" className="text-muted-foreground">
                  {t('rr.form.targetFlow.placeholder', locale)}
                </option>
                {(flows?.items ?? []).map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
              <IconChevronDown size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-0.5">
                  <span className="text-sm font-medium text-foreground/80">{t('vs.agent.label', locale)}</span>
                  <span className="text-sm font-medium text-destructive">*</span>
                </div>
                <VoiceSpeedAgentSelect
                  value={vsAgentId}
                  agentName={vsAgentName}
                  onChange={(id, n) => {
                    setVsAgentId(id)
                    setVsAgentName(n)
                  }}
                  onStatusChange={setVsStatus}
                />
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-0.5">
                  <span className="text-sm font-medium text-foreground/80">{t('rr.form.transferTarget', locale)}</span>
                  <span className="text-sm font-medium text-destructive">*</span>
                </div>
                <TransferTargetPicker value={transferTarget} onChange={setTransferTarget} />
                <p className="text-[13px] text-muted-foreground">{t('rr.form.transferTarget.hint', locale)}</p>
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={leaveConfirmOpen}
        title={t('rr.form.leaveTitle', locale)}
        message={t('rr.form.leaveConfirm', locale)}
        confirmLabel={t('rr.form.leaveOk', locale)}
        cancelLabel={t('rr.form.leaveCancel', locale)}
        variant="destructive"
        onCancel={() => setLeaveConfirmOpen(false)}
        onConfirm={() => {
          setLeaveConfirmOpen(false)
          router.push('/flow-studio/routing-rules')
        }}
      />
    </div>
  )
}

/**
 * Single human-handoff target picker — mirrors the queue-target selector used
 * by the assign_queue voice-flow node (user field / employee / employee group),
 * but limited to one target as required for direct VoiceSpeed routing.
 */
function TransferTargetPicker({
  value,
  onChange,
}: {
  value: AssignQueueTarget
  onChange: (next: AssignQueueTarget) => void
}) {
  const { locale } = useLocaleStore()
  const { data: groups } = useEmployeeGroups({ page: 1, per_page: 200 })
  const { data: employees } = useEmployeeSelect({ page: 1, per_page: 200 })
  const { data: userFields } = useUnifiedFields({
    domain: FieldDomain.USER,
    include_metadata: false,
  })
  const queueFields =
    userFields?.items.filter(
      (field) =>
        field.id != null &&
        field.status === 'active' &&
        (field.field_type === FieldType.EMPLOYEE_SELECT ||
          field.field_type === FieldType.GROUP_SELECT)
    ) ?? []

  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)] gap-2">
      <div className="relative">
        <select
          value={value.queue_type}
          onChange={(e) =>
            onChange({ queue_type: e.target.value as AssignQueueTargetType, queue_id: null })
          }
          className="h-10 w-full appearance-none rounded-lg border border-border bg-white px-3 pr-8 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="employee_group">{t('rr.form.transfer.type.group', locale)}</option>
          <option value="employee">{t('rr.form.transfer.type.employee', locale)}</option>
          <option value="user_field">{t('rr.form.transfer.type.userField', locale)}</option>
        </select>
        <IconChevronDown size={16} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
      </div>

      <div className="relative min-w-0">
        <select
          value={value.queue_id ?? ''}
          onChange={(e) =>
            onChange({ ...value, queue_id: e.target.value ? Number(e.target.value) : null })
          }
          className="h-10 w-full appearance-none rounded-lg border border-border bg-white px-3 pr-8 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">
            {value.queue_type === 'employee'
              ? t('rr.form.transfer.placeholder.employee', locale)
              : value.queue_type === 'user_field'
                ? t('rr.form.transfer.placeholder.userField', locale)
                : t('rr.form.transfer.placeholder.group', locale)}
          </option>
          {value.queue_type === 'employee'
            ? (employees?.items ?? []).map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.display_name || emp.username}
                </option>
              ))
            : value.queue_type === 'user_field'
              ? queueFields.map((field) => (
                  <option key={field.id} value={field.id ?? ''}>
                    {field.name}
                  </option>
                ))
              : (groups?.items ?? []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
        </select>
        <IconChevronDown size={16} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
      </div>
    </div>
  )
}
