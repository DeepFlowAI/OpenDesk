'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { SessionRecordDetail } from '@/models/session-record'
import { SessionSummaryFields } from '@/app/components/features/session-summary/session-summary-fields'
import { useSessionRecordSatisfaction } from '@/service/use-satisfaction-survey'
import type { SatisfactionSurveyResult } from '@/models/satisfaction-survey'

export type SessionInfoTab = 'basic' | 'summary'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

function formatDuration(startStr: string | null, endStr: string | null, locale: Locale): string {
  if (!startStr) return '-'
  const start = new Date(startStr).getTime()
  const end = endStr ? new Date(endStr).getTime() : Date.now()
  const diff = Math.max(0, Math.floor((end - start) / 1000))
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  const s = diff % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

type Props = {
  record: SessionRecordDetail
  onSummaryDirtyChange?: (dirty: boolean) => void
  activeTab?: SessionInfoTab
  onActiveTabChange?: (tab: SessionInfoTab) => void
}

export function SessionInfoPanel({ record, onSummaryDirtyChange, activeTab: controlledActiveTab, onActiveTabChange }: Props) {
  const { locale } = useLocaleStore()
  const [internalActiveTab, setInternalActiveTab] = useState<SessionInfoTab>('basic')
  const [summaryDirty, setSummaryDirty] = useState(false)
  const activeTab = controlledActiveTab ?? internalActiveTab

  const handleSummaryDirtyChange = (dirty: boolean) => {
    setSummaryDirty(dirty)
    onSummaryDirtyChange?.(dirty)
  }

  const switchTab = (nextTab: SessionInfoTab) => {
    if (activeTab === 'summary' && nextTab !== 'summary' && summaryDirty) {
      const confirmed = window.confirm(t('ws.summary.unsavedConfirm', locale))
      if (!confirmed) return
    }
    if (onActiveTabChange) {
      onActiveTabChange(nextTab)
    } else {
      setInternalActiveTab(nextTab)
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden p-5">
      <div className="mb-4 flex rounded-lg border border-border bg-background p-0.5">
        <button
          type="button"
          onClick={() => switchTab('basic')}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', activeTab === 'basic' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
        >
          {t('ws.summary.tab.basic', locale)}
        </button>
        <button
          type="button"
          onClick={() => switchTab('summary')}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', activeTab === 'summary' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
        >
          {t('ws.summary.tab.summary', locale)}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === 'basic' ? (
          <>
            <div className="mb-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('ws.records.sessions.detail.userInfo', locale)}
              </h3>
              <div className="flex flex-col gap-3">
                <InfoRow label={t('ws.records.sessions.detail.userName', locale)} value={record.visitor?.name || '-'} />
              </div>
            </div>

            <div className="mb-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('ws.records.sessions.detail.sessionInfo', locale)}
              </h3>
              <div className="flex flex-col gap-3">
                <InfoRow label={t('ws.records.sessions.detail.shareCode', locale)} value={record.share_code || record.public_id || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.channelType', locale)} value={record.channel?.channel_type || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.channelName', locale)} value={record.channel?.name || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.agent', locale)} value={record.agent?.display_name || record.agent?.name || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.startTime', locale)} value={formatDateTime(record.started_at)} />
                <InfoRow
                  label={t('ws.records.sessions.detail.endTime', locale)}
                  value={record.ended_at ? formatDateTime(record.ended_at) : t('ws.records.sessions.status.active', locale)}
                />
                <InfoRow label={t('ws.records.sessions.detail.duration', locale)} value={formatDuration(record.started_at, record.ended_at, locale)} />
              </div>
            </div>

            <SatisfactionRecordPanel recordId={record.id} />
          </>
        ) : activeTab === 'summary' ? (
          <SessionSummaryFields conversationId={record.id} onDirtyChange={handleSummaryDirtyChange} />
        ) : null}
      </div>
    </div>
  )
}

function resultLabel(result: SatisfactionSurveyResult | null, locale: Locale): string {
  if (!result) return '-'
  return result.option_name || '-'
}

function SatisfactionRecordPanel({ recordId }: { recordId: number }) {
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, refetch } = useSessionRecordSatisfaction(recordId)
  const record = data?.record
  const hasResult = Boolean(record?.service_result || record?.product_result)

  return (
    <div>
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {t('ws.summary.tab.satisfaction', locale)}
      </h3>

      {isLoading ? (
        <PanelState text={t('ws.records.sessions.satisfaction.loading', locale)} />
      ) : isError ? (
        <div className="space-y-3">
          <PanelState text={t('ws.records.sessions.satisfaction.loadFailed', locale)} />
          <button
            type="button"
            onClick={() => refetch()}
            className="h-8 rounded-md border border-border px-3 text-xs text-foreground hover:bg-muted"
          >
            {t('ws.chat.retry', locale)}
          </button>
        </div>
      ) : hasResult ? (
        <SatisfactionResultCard
          serviceResult={record?.service_result ?? null}
          productResult={record?.product_result ?? null}
          submittedAt={record?.submitted_at ?? null}
          locale={locale}
        />
      ) : (
        <PanelState text={t('ws.records.sessions.satisfaction.empty', locale)} />
      )}
    </div>
  )
}

function PanelState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground">
      {text}
    </div>
  )
}

function SatisfactionResultCard({
  serviceResult,
  productResult,
  submittedAt,
  locale,
}: {
  serviceResult: SatisfactionSurveyResult | null
  productResult: SatisfactionSurveyResult | null
  submittedAt: string | null
  locale: Locale
}) {
  const results = [
    serviceResult ? { key: 'service', typeLabel: t('ws.records.sessions.satisfaction.service', locale), result: serviceResult } : null,
    productResult ? { key: 'product', typeLabel: t('ws.records.sessions.satisfaction.product', locale), result: productResult } : null,
  ].filter((item): item is { key: string; typeLabel: string; result: SatisfactionSurveyResult } => item !== null)
  const displaySubmittedAt = submittedAt ?? serviceResult?.submitted_at ?? productResult?.submitted_at ?? null

  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-foreground">
          {t('ws.records.sessions.satisfaction.result', locale)}
        </h3>
      </div>
      <div className="space-y-4">
        {results.map((item, index) => (
          <div key={item.key} className={cn('space-y-3', index > 0 && 'border-t border-border pt-4')}>
            <div className="text-xs font-medium text-muted-foreground">{item.typeLabel}</div>
            {item.result.type === 'service' && (
              <InfoRow
                label={t('ws.records.sessions.satisfaction.resolved', locale)}
                value={item.result.resolved == null ? t('ws.records.sessions.satisfaction.notEnabled', locale) : item.result.resolved ? t('ws.records.sessions.satisfaction.resolved', locale) : t('ws.records.sessions.satisfaction.unresolved', locale)}
              />
            )}
            <InfoRow label={t('ws.records.sessions.satisfaction.rating', locale)} value={resultLabel(item.result, locale)} />
            <InfoRow label={t('ws.records.sessions.satisfaction.labels', locale)} value={item.result.labels.length ? item.result.labels.join('、') : '-'} />
            <InfoRow label={t('ws.records.sessions.satisfaction.remark', locale)} value={item.result.remark || '-'} />
          </div>
        ))}
        <div className="border-t border-border pt-4">
          <InfoRow label={t('ws.records.sessions.satisfaction.submittedAt', locale)} value={formatDateTime(displaySubmittedAt)} />
        </div>
      </div>
    </div>
  )
}

function InfoRow({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="break-words text-sm text-foreground">{value}</span>
      </div>
    </div>
  )
}
