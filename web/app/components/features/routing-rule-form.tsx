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
import type { RoutingCondition, RoutingConditionType } from '@/models/inbound-routing-rule'
import { useServiceHours } from '@/service/use-service-hours'
import { useVoiceFlowsSelect } from '@/service/use-voice-flows'
import {
  useInboundRoutingRule,
  useCreateInboundRoutingRule,
  useUpdateInboundRoutingRule,
} from '@/service/use-inbound-routing-rules'

type RowState = RoutingCondition & { _key: string }

function newKey() {
  return `k-${Math.random().toString(36).slice(2, 11)}`
}

function defaultRow(): RowState {
  return { _key: newKey(), condition_type: 'caller_number', operator: 'eq', value: '' }
}

function normalizeOperators(ct: RoutingConditionType): string[] {
  if (ct === 'call_time') return ['in_schedule', 'not_in_schedule']
  return ['eq', 'ne']
}

function opLabel(op: string, locale: import('@/context/locale-store').Locale): string {
  if (op === 'eq') return t('rr.cond.op.eq', locale)
  if (op === 'ne') return t('rr.cond.op.ne', locale)
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
  const createMut = useCreateInboundRoutingRule()
  const updateMut = useUpdateInboundRoutingRule()

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [targetFlowId, setTargetFlowId] = useState<number | ''>('')
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
    setTargetFlowId(rule.target_voice_flow_id)
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
      setSavedSnapshot(
        JSON.stringify({
          name: rule.name.trim(),
          enabled: rule.enabled,
          target: rule.target_voice_flow_id,
          conditions: rule.conditions ?? [],
        })
      )
    }
  }, [isNew, rule, initialized])

  const payloadForCompare = useMemo(
    () =>
      JSON.stringify({
        name: name.trim(),
        enabled,
        target: targetFlowId === '' ? '' : Number(targetFlowId),
        conditions: rows.map(({ _key: _, ...c }) => c),
      }),
    [name, enabled, targetFlowId, rows]
  )

  const emptyNewSnapshot = '{"name":"","enabled":true,"target":"","conditions":[]}'
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
    if (targetFlowId === '') {
      toast.error(t('rr.form.validation.flow', locale))
      return
    }
    const conditions: RoutingCondition[] = rows.map(({ _key: _, ...c }) => c)
    const body = { name: tn, enabled, conditions, target_voice_flow_id: Number(targetFlowId) }
    try {
      if (isNew) {
        await createMut.mutateAsync(body)
        toast.success(t('rr.form.saveSuccess', locale))
        router.push('/flow-studio/routing-rules')
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: body })
        toast.success(t('rr.form.saveSuccess', locale))
        setSavedSnapshot(JSON.stringify({ name: tn, enabled, target: Number(targetFlowId), conditions }))
      }
    } catch {
      toast.error(t('rr.form.saveFailed', locale))
    }
  }

  const saveDisabled = createMut.isPending || updateMut.isPending || !isDirty || !name.trim() || targetFlowId === ''

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
                  <div className="relative w-[90px] shrink-0">
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

        {/* Target voice flow */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground/80">{t('rr.form.targetFlow', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>
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
