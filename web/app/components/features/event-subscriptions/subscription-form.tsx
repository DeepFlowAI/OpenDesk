'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { EventSubscription, EventSubscriptionSecretResponse, EventSubscriptionTestResult } from '@/models/event-subscription'
import {
  useCreateEventSubscription,
  useEventSubscription,
  useRotateEventSubscriptionSecret,
  useTestEventSubscription,
  useUpdateEventSubscription,
} from '@/service/use-event-subscriptions'
import { validateEventSubscriptionForm, type EventSubscriptionFormValue } from '@/utils/event-subscription-validation'
import { SubscriptionBasicSection, SubscriptionSecuritySection } from '@/app/components/features/event-subscriptions/subscription-form-sections'
import { SubscriptionConfirmDialog, SubscriptionSecretDialog, type SubscriptionConfirmTarget } from '@/app/components/features/event-subscriptions/dialogs'

const EMPTY: EventSubscriptionFormValue = { name: '', endpoint_url: '', description: '' }
const snapshot = (value: EventSubscriptionFormValue) => JSON.stringify(value)
const fromRecord = (record: EventSubscription): EventSubscriptionFormValue => ({ name: record.name, endpoint_url: record.endpoint_url, description: record.description ?? '' })

export function SubscriptionForm({ subscriptionId }: { subscriptionId: string | null }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const detail = useEventSubscription(subscriptionId)
  const create = useCreateEventSubscription()
  const update = useUpdateEventSubscription()
  const rotate = useRotateEventSubscriptionSecret()
  const test = useTestEventSubscription()
  const [form, setForm] = useState<EventSubscriptionFormValue>(EMPTY)
  const [saved, setSaved] = useState(snapshot(EMPTY))
  const [record, setRecord] = useState<EventSubscription | null>(null)
  const [secret, setSecret] = useState<EventSubscriptionSecretResponse | null>(null)
  const [createdId, setCreatedId] = useState<string | null>(null)
  const [confirmTarget, setConfirmTarget] = useState<SubscriptionConfirmTarget | null>(null)
  const [testResult, setTestResult] = useState<EventSubscriptionTestResult | null>(null)
  const [showErrors, setShowErrors] = useState(false)
  const hydratedId = useRef<string | null>(null)
  const validation = useMemo(() => validateEventSubscriptionForm(form), [form])
  const dirty = snapshot(form) !== saved
  const saving = create.isPending || update.isPending

  useEffect(() => {
    if (!detail.data) return
    setRecord(detail.data)
    if (hydratedId.current === detail.data.public_id) return
    const value = fromRecord(detail.data)
    setForm(value)
    setSaved(snapshot(value))
    hydratedId.current = detail.data.public_id
  }, [detail.data])
  useEffect(() => {
    const unload = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault() }
    const pop = () => { if (dirty && !window.confirm(t('eventSubs.leaveConfirm', locale))) window.history.forward() }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('popstate', pop)
    return () => { window.removeEventListener('beforeunload', unload); window.removeEventListener('popstate', pop) }
  }, [dirty, locale])

  const goBack = () => {
    if (dirty && !window.confirm(t('eventSubs.leaveConfirm', locale))) return
    router.push('/event-subscriptions')
  }
  const save = async () => {
    setShowErrors(true)
    if (!validation.data) return
    const payload = { ...validation.data, description: validation.data.description || null }
    try {
      if (record) {
        const result = await update.mutateAsync({ id: record.public_id, data: payload })
        const value = fromRecord(result)
        setRecord(result); setForm(value); setSaved(snapshot(value))
        toast.success(t('eventSubs.save.success', locale))
      } else {
        const result = await create.mutateAsync(payload)
        const value = fromRecord(result.record)
        setRecord(result.record); setForm(value); setSaved(snapshot(value)); setSecret(result); setCreatedId(result.record.public_id)
        toast.success(t('eventSubs.create.success', locale))
      }
      setShowErrors(false)
    } catch { toast.error(t('eventSubs.save.failed', locale)) }
  }
  const confirmRotate = async () => {
    if (!record) return
    try { const result = await rotate.mutateAsync(record.public_id); setRecord(result.record); setSecret(result); setConfirmTarget(null) }
    catch { toast.error(t('eventSubs.operation.failed', locale)) }
  }
  const sendTest = async () => {
    if (!record) return
    try {
      const result = await test.mutateAsync(record.public_id)
      setTestResult(result)
      if (result.status === 'succeeded') toast.success(t('eventSubs.test.succeeded', locale))
      else toast.error(t('eventSubs.test.failed', locale))
    }
    catch { toast.error(t('eventSubs.test.failed', locale)) }
  }

  if (subscriptionId && detail.isLoading) return <div className="h-96 animate-pulse rounded-lg bg-muted" />
  if (subscriptionId && detail.isError) return <div className="rounded-lg border border-destructive/30 p-6 text-sm text-destructive">{t('eventSubs.load.failed', locale)}</div>
  const errors = (showErrors
    ? Object.fromEntries(Object.entries(validation.errors).map(([key, value]) => [key, t(`eventSubs.validation.${value}`, locale)]))
    : {}) as Partial<Record<keyof EventSubscriptionFormValue, string>>
  return (
    <div className="-m-8 flex flex-col">
      <header className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button className="flex items-center gap-3" onClick={goBack}><IconArrowLeft size={20} className="text-muted-foreground" /><span className="text-base font-semibold">{t(record ? 'eventSubs.edit' : 'eventSubs.create', locale)}</span>{record && <span className="rounded-md bg-muted px-2 py-1 text-xs">{t(record.is_active ? 'eventSubs.status.active' : 'eventSubs.status.disabled', locale)}</span>}</button>
        <button className="h-9 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={!dirty || !validation.data || saving} onClick={() => void save()}>{saving ? t('eventSubs.pending', locale) : t('eventSubs.save', locale)}</button>
      </header>
      <div className="px-8"><div className="max-w-[840px]">
        <SubscriptionBasicSection value={form} errors={errors} locale={locale} onChange={(field, value) => setForm((current) => ({ ...current, [field]: value }))} />
        <SubscriptionSecuritySection record={record} locale={locale} endpointChanged={Boolean(record && form.endpoint_url !== record.endpoint_url)} testResult={testResult} rotating={rotate.isPending} testing={test.isPending} onRotate={() => record && setConfirmTarget({ action: 'rotate', item: record })} onTest={() => void sendTest()} />
      </div></div>
      <SubscriptionConfirmDialog target={confirmTarget} pending={rotate.isPending} onCancel={() => setConfirmTarget(null)} onConfirm={() => void confirmRotate()} />
      <SubscriptionSecretDialog value={secret} onClose={() => { setSecret(null); if (createdId) router.replace(`/event-subscriptions/${createdId}`) }} />
    </div>
  )
}
