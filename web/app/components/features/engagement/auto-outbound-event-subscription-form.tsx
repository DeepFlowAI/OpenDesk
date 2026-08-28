'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Locale } from '@/context/locale-store'
import type { AutoOutboundEventSubscription } from '@/models/auto-outbound-task'
import { useSaveAutoOutboundEventSubscription } from '@/service/use-auto-outbound-tasks'
import { t } from '@/utils/i18n'
import { AutoOutboundEventOptions } from '@/app/components/features/engagement/auto-outbound-event-options'

export function AutoOutboundEventSubscriptionForm({
  taskId,
  locale,
  configuration,
  onCancel,
  onDirtyChange,
}: {
  taskId: number
  locale: Locale
  configuration: AutoOutboundEventSubscription
  onCancel: (force?: boolean) => void
  onDirtyChange: (dirty: boolean) => void
}) {
  const [enabled, setEnabled] = useState(configuration.enabled)
  const [subscriptionId, setSubscriptionId] = useState(configuration.binding?.subscription_public_id ?? '')
  const [eventTypes, setEventTypes] = useState(configuration.binding?.event_types ?? [])
  const [submitted, setSubmitted] = useState(false)
  const save = useSaveAutoOutboundEventSubscription(taskId)
  const initial = useMemo(() => JSON.stringify({
    enabled: configuration.enabled,
    subscriptionId: configuration.binding?.subscription_public_id ?? '',
    eventTypes: configuration.binding?.event_types ?? [],
  }), [configuration])
  const dirty = JSON.stringify({ enabled, subscriptionId, eventTypes }) !== initial
  const endpointError = submitted && enabled && !subscriptionId
  const eventsError = submitted && enabled && eventTypes.length === 0
  const endpointItems = useMemo(
    () => Object.fromEntries(configuration.options.map((option) => [
      option.public_id,
      `${option.name}${option.is_active ? '' : ` (${t('ws.autoOutbound.subscription.disabled', locale)})`}`,
    ])),
    [configuration.options, locale],
  )

  useEffect(() => {
    onDirtyChange(dirty)
  }, [dirty, onDirtyChange])

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  const cancel = () => {
    onCancel()
  }
  const submit = async () => {
    setSubmitted(true)
    if (enabled && (!subscriptionId || eventTypes.length === 0)) return
    try {
      await save.mutateAsync({
        enabled,
        subscription_public_id: enabled ? subscriptionId : null,
        event_types: enabled ? eventTypes : [],
      })
      toast.success(t('ws.autoOutbound.subscription.saved', locale))
      onCancel(true)
    } catch {
      toast.error(t('ws.autoOutbound.subscription.saveFailed', locale))
    }
  }

  return (
    <>
      <main className="min-h-0 flex-1 overflow-auto bg-muted/20 p-6">
        <section className="mx-auto max-w-3xl rounded-lg border border-border bg-background p-5">
          <div className="flex items-start justify-between gap-6">
            <div>
              <h2 className="text-base font-semibold">{t('ws.autoOutbound.subscription.sectionTitle', locale)}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{t('ws.autoOutbound.subscription.sectionDesc', locale)}</p>
            </div>
            <label className="flex items-center gap-2 text-sm font-medium">
              {t('ws.autoOutbound.subscription.enable', locale)}
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </label>
          </div>
          {enabled && (
            <div className="mt-5 space-y-5">
              <div className="space-y-2">
                <label htmlFor="subscription-endpoint" className="text-sm font-medium">
                  {t('ws.autoOutbound.subscription.endpoint', locale)}
                </label>
                <Select items={endpointItems} value={subscriptionId || null} onValueChange={(value) => setSubscriptionId(value ?? '')}>
                  <SelectTrigger id="subscription-endpoint" className="w-full" aria-invalid={endpointError}>
                    <SelectValue placeholder={t('ws.autoOutbound.subscription.selectEndpoint', locale)} />
                  </SelectTrigger>
                  <SelectContent>
                    {configuration.options.map((option) => (
                      <SelectItem key={option.public_id} value={option.public_id}>
                        {option.name}{option.is_active ? '' : ` (${t('ws.autoOutbound.subscription.disabled', locale)})`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {endpointError && <p className="text-xs text-destructive">{t('ws.autoOutbound.subscription.endpointRequired', locale)}</p>}
                {configuration.options.length === 0 && (configuration.can_manage_global ? <Link href="/event-subscriptions/new" className="text-xs text-primary hover:underline">{t('ws.autoOutbound.subscription.createGlobal', locale)}</Link> : <p className="text-xs text-muted-foreground">{t('ws.autoOutbound.subscription.contactAdmin', locale)}</p>)}
              </div>
              <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs leading-5 text-muted-foreground">{t('ws.autoOutbound.subscription.sensitiveHint', locale)}</div>
              <AutoOutboundEventOptions locale={locale} selected={eventTypes} onChange={setEventTypes} error={eventsError ? t('ws.autoOutbound.subscription.eventsRequired', locale) : undefined} />
            </div>
          )}
          {!enabled && configuration.enabled && dirty && <p className="mt-4 text-sm text-warning">{t('ws.autoOutbound.subscription.disableWarning', locale)}</p>}
        </section>
      </main>
      <footer className="flex shrink-0 justify-end gap-2 border-t border-border bg-background px-6 py-4">
        <Button type="button" variant="outline" size="lg" onClick={cancel}>{t('ws.autoOutbound.subscription.cancel', locale)}</Button>
        <Button type="button" size="lg" onClick={() => void submit()} disabled={!dirty || save.isPending}>{save.isPending ? t('ws.autoOutbound.subscription.saving', locale) : t('ws.autoOutbound.subscription.save', locale)}</Button>
      </footer>
    </>
  )
}
