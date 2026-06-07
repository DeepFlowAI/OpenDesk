'use client'

import { useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useQueuePolicies, useUpsertQueuePolicy } from '@/service/use-queue-policies'
import { QueuePolicyForm } from '@/app/components/features/queue-settings/queue-policy-form'
import type { QueueChannel, QueuePolicy, QueuePolicyUpsertPayload } from '@/models/queue-policy'

function findPolicy(policies: QueuePolicy[] | undefined, channel: QueueChannel): QueuePolicy | undefined {
  return policies?.find((policy) => policy.channel === channel)
}

export default function QueueSettingsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading, isError } = useQueuePolicies({ scope_type: 'global' })
  const upsertMutation = useUpsertQueuePolicy()
  const [savingChannel, setSavingChannel] = useState<QueueChannel | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const policies = useMemo(() => data?.items ?? [], [data])

  const handleSave = async (payload: QueuePolicyUpsertPayload) => {
    try {
      setSavingChannel(payload.channel)
      await upsertMutation.mutateAsync(payload)
      setToast({ type: 'success', text: t('queue.saveSuccess', locale) })
    } catch {
      setToast({ type: 'error', text: t('queue.saveFailed', locale) })
    } finally {
      setSavingChannel(null)
      setTimeout(() => setToast(null), 3000)
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('queue.loading', locale)}</p>
      </div>
    )
  }

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold text-foreground">{t('queue.page.title', locale)}</h1>
        <p className="text-sm text-muted-foreground">{t('queue.page.description', locale)}</p>
      </div>

      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      {isError && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {t('queue.loadFailed', locale)}
        </div>
      )}

      <div className="flex flex-col gap-8">
        <QueuePolicyForm
          channel="online_chat"
          title={t('queue.default.onlineTitle', locale)}
          policy={findPolicy(policies, 'online_chat')}
          saving={savingChannel === 'online_chat'}
          onSave={handleSave}
        />
        <QueuePolicyForm
          channel="call_center"
          title={t('queue.default.callTitle', locale)}
          policy={findPolicy(policies, 'call_center')}
          saving={savingChannel === 'call_center'}
          onSave={handleSave}
        />
      </div>
    </div>
  )
}
