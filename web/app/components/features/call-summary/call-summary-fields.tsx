'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { SummaryUsageFields } from '@/app/components/features/summary-usage/summary-usage-fields'
import { useCallSummaryUsage, useUpdateCallSummaryFieldValue } from '@/service/use-call-summary'

type Props = {
  callRecordId: number | null | undefined
  onDirtyChange?: (dirty: boolean) => void
}

export function CallSummaryFields({ callRecordId, onDirtyChange }: Props) {
  const { locale } = useLocaleStore()
  const summaryQuery = useCallSummaryUsage(callRecordId)
  const updateField = useUpdateCallSummaryFieldValue()
  const hasCallRecord = typeof callRecordId === 'number'

  return (
    <SummaryUsageFields
      fields={summaryQuery.data?.fields}
      rules={summaryQuery.data?.rules}
      values={summaryQuery.data?.values}
      isLoading={summaryQuery.isLoading}
      isError={summaryQuery.isError}
      isSaving={updateField.isPending}
      texts={{
        loading: t('callSummary.usage.loading', locale),
        loadFailed: t('callSummary.usage.loadFailed', locale),
        empty: t('callSummary.usage.empty', locale),
        retry: t('ws.chat.retry', locale),
        fieldRequired: t('ws.chat.fieldRequired', locale),
        saveFailed: t('callSummary.usage.saveFailed', locale),
        editField: t('ws.chat.editField', locale),
        unavailable: hasCallRecord ? undefined : t('callSummary.usage.unavailable', locale),
      }}
      onRetry={() => void summaryQuery.refetch()}
      onSaveField={(data) => {
        if (typeof callRecordId !== 'number') return Promise.resolve()
        return updateField.mutateAsync({ callRecordId, data })
      }}
      onDirtyChange={onDirtyChange}
    />
  )
}
