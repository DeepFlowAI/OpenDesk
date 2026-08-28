'use client'

import { IconArrowLeft } from '@tabler/icons-react'
import { HTTPError } from 'ky'
import { useParams, useRouter } from 'next/navigation'
import { useCallback, useState } from 'react'
import { AutoOutboundEventSubscriptionForm } from '@/app/components/features/engagement/auto-outbound-event-subscription-form'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import { TableSkeleton } from '@/app/components/features/engagement/auto-outbound-task-ui'
import { useLocaleStore } from '@/context/locale-store'
import { useAutoOutboundEventSubscription } from '@/service/use-auto-outbound-tasks'
import { t } from '@/utils/i18n'
import { Button } from '@/components/ui/button'

export default function AutoOutboundEventSubscriptionPage() {
  const taskId = Number(useParams().taskId)
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [dirty, setDirty] = useState(false)
  const query = useAutoOutboundEventSubscription(taskId)
  const back = useCallback((force = false) => {
    if (!force && dirty && !window.confirm(t('ws.autoOutbound.subscription.leaveConfirm', locale))) {
      return
    }
    router.push(`/workspace/engagement/auto-outbound-tasks/${taskId}`)
  }, [dirty, locale, router, taskId])
  const status = query.error instanceof HTTPError ? query.error.response.status : 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b border-border bg-background px-6 py-4">
        <Button type="button" variant="ghost" size="icon" onClick={() => back()} aria-label={t('ws.autoOutbound.detail.back', locale)}><IconArrowLeft size={18} /></Button>
        <div>
          <h1 className="text-xl font-semibold">{t('ws.autoOutbound.subscription.title', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{query.data?.task_name ?? '—'}</p>
        </div>
      </header>
      {query.isLoading ? (
        <main className="flex-1 p-6"><TableSkeleton rows={5} cols={2} /></main>
      ) : query.isError || !query.data ? (
        <main className="flex-1 p-6"><EmptyState title={status === 403 ? t('ws.autoOutbound.forbidden', locale) : t('ws.autoOutbound.subscription.loadFailed', locale)} action={<Button type="button" onClick={() => void query.refetch()}>{t('ws.autoOutbound.subscription.retry', locale)}</Button>} /></main>
      ) : (
        <AutoOutboundEventSubscriptionForm taskId={taskId} locale={locale} configuration={query.data} onCancel={back} onDirtyChange={setDirty} />
      )}
    </div>
  )
}
