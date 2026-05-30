'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { SummaryUsageFields } from '@/app/components/features/summary-usage/summary-usage-fields'
import { useSessionSummaryUsage, useUpdateSessionSummaryFieldValue } from '@/service/use-session-summary'

type Props = {
  conversationId: number
  onDirtyChange?: (dirty: boolean) => void
}

export function SessionSummaryFields({ conversationId, onDirtyChange }: Props) {
  const { locale } = useLocaleStore()
  const summaryQuery = useSessionSummaryUsage(conversationId)
  const updateField = useUpdateSessionSummaryFieldValue()

  return (
    <SummaryUsageFields
      fields={summaryQuery.data?.fields}
      rules={summaryQuery.data?.rules}
      values={summaryQuery.data?.values}
      isLoading={summaryQuery.isLoading}
      isError={summaryQuery.isError}
      isSaving={updateField.isPending}
      texts={{
        loading: t('ws.summary.loading', locale),
        loadFailed: t('ws.summary.loadFailed', locale),
        empty: t('ws.summary.empty', locale),
        retry: t('ws.chat.retry', locale),
        fieldRequired: t('ws.chat.fieldRequired', locale),
        saveFailed: t('ws.summary.saveFailed', locale),
        editField: t('ws.chat.editField', locale),
      }}
      onRetry={() => void summaryQuery.refetch()}
      onSaveField={(data) => updateField.mutateAsync({ conversationId, data })}
      onDirtyChange={onDirtyChange}
    />
  )
}
