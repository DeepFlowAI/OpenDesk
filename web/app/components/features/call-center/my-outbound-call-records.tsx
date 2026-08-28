'use client'

import { useState } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'

import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import { useLocaleStore } from '@/context/locale-store'
import type { MyOutboundTargetRecordsResponse } from '@/models/outbound-task'
import { t } from '@/utils/i18n'

function formatRecordTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatRecordDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function MyOutboundCallRecords({
  recordsQuery,
}: {
  recordsQuery: UseQueryResult<MyOutboundTargetRecordsResponse>
}) {
  const { locale } = useLocaleStore()
  const [detailRecordId, setDetailRecordId] = useState<string | null>(null)
  const items = recordsQuery.data?.items ?? []

  if (recordsQuery.isLoading) {
    return <p className="p-2 text-sm text-muted-foreground">{t('ws.outboundExec.records.loading', locale)}</p>
  }
  if (items.length === 0) {
    return (
      <div className="grid h-20 place-items-center rounded-lg border border-dashed border-border text-xs text-muted-foreground">
        {t('ws.outboundExec.records.empty', locale)}
      </div>
    )
  }

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/60">
              <th className="px-3 py-2 font-medium text-muted-foreground">{t('ws.outboundExec.records.col.time', locale)}</th>
              <th className="px-3 py-2 font-medium text-muted-foreground">{t('ws.outboundExec.records.col.result', locale)}</th>
              <th className="px-3 py-2 font-medium text-muted-foreground">{t('ws.outboundExec.records.col.duration', locale)}</th>
              <th className="px-3 py-2 font-medium text-muted-foreground">{t('ws.outboundExec.records.col.agent', locale)}</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">{t('ws.outboundExec.records.col.action', locale)}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const resultLabel = item.result || (item.answered
                ? t('ws.outboundExec.records.answered', locale)
                : t('ws.outboundExec.records.unanswered', locale))
              return (
                <tr key={`${item.source}-${item.id}`} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-2 font-mono text-[11px]">{formatRecordTime(item.started_at)}</td>
                  <td className="px-3 py-2">
                    <span className={item.answered ? 'font-medium text-success' : 'text-muted-foreground'}>
                      {resultLabel}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                    {item.answered && item.duration_ms != null ? formatRecordDuration(item.duration_ms) : '—'}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{item.agent_name || '—'}</td>
                  <td className="px-3 py-2 text-right">
                    {item.can_view_detail && item.call_record_public_id ? (
                      <button
                        type="button"
                        onClick={() => setDetailRecordId(item.call_record_public_id)}
                        className="font-medium text-primary hover:underline"
                      >
                        {t('ws.outboundExec.records.detail', locale)}
                      </button>
                    ) : null}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {detailRecordId && (
        <CallRecordDetailDrawer recordId={detailRecordId} onClose={() => setDetailRecordId(null)} />
      )}
    </>
  )
}
