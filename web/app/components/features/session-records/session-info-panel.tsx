'use client'

import { useState } from 'react'
import { IconCopy, IconCheck } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { SessionRecordDetail } from '@/models/session-record'
import { SessionSummaryFields } from '@/app/components/features/session-summary/session-summary-fields'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

function formatDuration(startStr: string | null, endStr: string | null, locale: string): string {
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
}

export function SessionInfoPanel({ record, onSummaryDirtyChange }: Props) {
  const { locale } = useLocaleStore()
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'basic' | 'summary'>('basic')
  const [summaryDirty, setSummaryDirty] = useState(false)

  const handleCopy = (text: string, field: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field)
      setTimeout(() => setCopiedField(null), 2000)
    })
  }

  const handleSummaryDirtyChange = (dirty: boolean) => {
    setSummaryDirty(dirty)
    onSummaryDirtyChange?.(dirty)
  }

  const switchTab = (nextTab: 'basic' | 'summary') => {
    if (activeTab === 'summary' && nextTab !== 'summary' && summaryDirty) {
      const confirmed = window.confirm(t('ws.summary.unsavedConfirm', locale))
      if (!confirmed) return
    }
    setActiveTab(nextTab)
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
                <InfoRow label={t('ws.records.sessions.detail.userId', locale)} value={record.visitor ? String(record.visitor.id) : '-'} />
              </div>
            </div>

            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('ws.records.sessions.detail.sessionInfo', locale)}
              </h3>
              <div className="flex flex-col gap-3">
                <InfoRow
                  label={t('ws.records.sessions.detail.sessionId', locale)}
                  value={String(record.id)}
                  copyable
                  onCopy={(v) => handleCopy(v, 'sessionId')}
                  copied={copiedField === 'sessionId'}
                />
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
          </>
        ) : (
          <SessionSummaryFields conversationId={record.id} onDirtyChange={handleSummaryDirtyChange} />
        )}
      </div>
    </div>
  )
}

function InfoRow({
  label,
  value,
  copyable,
  onCopy,
  copied,
}: {
  label: string
  value: string
  copyable?: boolean
  onCopy?: (v: string) => void
  copied?: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="break-words text-sm text-foreground">{value}</span>
        {copyable && (
          <button
            onClick={() => onCopy?.(value)}
            className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
          >
            {copied ? <IconCheck size={12} className="text-success" /> : <IconCopy size={12} />}
          </button>
        )}
      </div>
    </div>
  )
}
