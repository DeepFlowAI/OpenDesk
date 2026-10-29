'use client'

import { Fragment, useState } from 'react'

import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import {
  formatDateTime,
  formatDurationMs,
  receptionTypeLabel,
  TableSkeleton,
  TerminalStateBadge,
} from '@/app/components/features/engagement/auto-outbound-task-ui'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import type { Locale } from '@/context/locale-store'
import { summarizeReceptionResult } from '@/lib/auto-outbound-reception-result'
import type { AutoOutboundCallVariable, AutoOutboundRecord } from '@/models/auto-outbound-task'
import { t } from '@/utils/i18n'

function CallVariablesList({ locale, items }: { locale: Locale; items: AutoOutboundCallVariable[] }) {
  return (
    <div data-testid="auto-outbound-record-call-variables">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-sm font-medium text-foreground">
          {t('ws.autoOutbound.records.callVariables.title', locale)}
        </span>
        <span className="text-xs text-muted-foreground">
          {t('ws.autoOutbound.records.callVariables.hint', locale)}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-[minmax(120px,max-content)_1fr] gap-x-6 gap-y-1.5 text-sm">
        {items.map((item) => (
          <Fragment key={item.name}>
            <dt className="font-mono text-xs leading-5 text-muted-foreground">{item.name}</dt>
            <dd className="break-all text-foreground">
              {item.value || '—'}
              {item.truncated ? (
                <span className="ml-2 text-xs text-warning">
                  {t('ws.autoOutbound.records.callVariables.truncated', locale)}
                </span>
              ) : null}
            </dd>
          </Fragment>
        ))}
      </dl>
    </div>
  )
}

export function RecordsPanel({
  locale,
  loading,
  items,
  canViewCallRecord,
  onOpenTarget,
}: {
  locale: Locale
  loading: boolean
  items: AutoOutboundRecord[]
  canViewCallRecord: boolean
  onOpenTarget: (targetId: number) => void
}) {
  const [detailRecordId, setDetailRecordId] = useState<string | null>(null)
  const [expandedRecordId, setExpandedRecordId] = useState<number | null>(null)

  if (loading) return <TableSkeleton cols={8} />
  if (!items.length) return <EmptyState title={t('ws.autoOutbound.records.empty', locale)} />

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.phone', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.target', locale)}</th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {t('ws.autoOutbound.records.col.startedAt', locale)}
              </th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.terminal', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.reception', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.duration', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.result', locale)}</th>
              <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.records.col.detail', locale)}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((record) => {
              const resultSummary = summarizeReceptionResult(
                record.reception_result,
                record.reception_type,
                locale,
              )
              const publicId = record.call_record_public_id
              const callVariables = record.reception_type === 'bot' ? record.call_variables : null
              const variablesExpanded = callVariables?.status === 'passed' && expandedRecordId === record.id
              return (
                <Fragment key={record.id}>
                <tr className="border-t border-border">
                  <td className="px-4 py-3">{record.phone_number}</td>
                  <td className="px-4 py-3">
                    <button type="button" className="hover:underline" onClick={() => onOpenTarget(record.target_id)}>
                      #{record.target_id}
                    </button>
                  </td>
                  <td
                    data-testid="auto-outbound-record-started-at"
                    className="whitespace-nowrap px-4 py-3 text-muted-foreground"
                  >
                    {formatDateTime(record.started_at, true)}
                  </td>
                  <td className="px-4 py-3">
                    {record.terminal_state ? (
                      <TerminalStateBadge state={record.terminal_state} locale={locale} />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {record.reception_type
                      ? receptionTypeLabel(record.reception_type, record.agent_name, locale)
                      : '—'}
                  </td>
                  <td className="px-4 py-3">{formatDurationMs(record.duration_ms)}</td>
                  {callVariables ? (
                    <td
                      data-testid="auto-outbound-record-result"
                      className="max-w-[220px] px-4 py-3 text-muted-foreground"
                    >
                      <span className="block truncate" title={resultSummary}>{resultSummary}</span>
                      {callVariables.status === 'passed' ? (
                        <button
                          type="button"
                          data-testid="auto-outbound-record-call-variables-toggle"
                          aria-expanded={variablesExpanded}
                          className="mt-1 text-xs text-foreground hover:underline"
                          onClick={() => setExpandedRecordId(variablesExpanded ? null : record.id)}
                        >
                          {t('ws.autoOutbound.records.callVariables.toggle', locale, {
                            count: callVariables.items.length,
                          })}
                        </button>
                      ) : (
                        <p className="mt-1 text-xs text-warning">
                          {t('ws.autoOutbound.records.callVariables.failed', locale)}
                        </p>
                      )}
                    </td>
                  ) : (
                    <td
                      data-testid="auto-outbound-record-result"
                      className="max-w-[220px] truncate px-4 py-3 text-muted-foreground"
                      title={resultSummary}
                    >
                      {resultSummary}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    {canViewCallRecord && publicId ? (
                      <button
                        type="button"
                        data-testid="auto-outbound-record-call-detail"
                        className="text-sm hover:underline"
                        onClick={() => setDetailRecordId(publicId)}
                      >
                        {t('ws.autoOutbound.action.viewCall', locale)}
                      </button>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
                {variablesExpanded && callVariables ? (
                  <tr className="border-t border-border bg-muted/30">
                    <td colSpan={8} className="px-4 py-3">
                      <CallVariablesList locale={locale} items={callVariables.items} />
                    </td>
                  </tr>
                ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      {detailRecordId ? (
        <CallRecordDetailDrawer recordId={detailRecordId} onClose={() => setDetailRecordId(null)} />
      ) : null}
    </>
  )
}
