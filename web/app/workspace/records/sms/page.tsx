'use client'
/**
 * SMS send records page — list + phone/status filters + detail drawer.
 */
import Link from 'next/link'
import { useMemo, useState } from 'react'
import {
  IconLoader2,
  IconSearch,
  IconX,
} from '@tabler/icons-react'

import { useSmsSendRecord, useSmsSendRecords } from '@/service/use-sms'
import type { SmsSendRecordItem, SmsSendSource, SmsSendStatus } from '@/models/sms'
import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { hasAnyPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'

const PER_PAGE_OPTIONS = [20, 50, 100]
const STATUS_OPTIONS: SmsSendStatus[] = ['delivered', 'failed', 'submitted', 'pending']
const SOURCE_OPTIONS: SmsSendSource[] = ['single', 'bulk']

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function statusTone(status: SmsSendStatus): string {
  if (status === 'delivered') return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
  if (status === 'failed') return 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'
  if (status === 'submitted' || status === 'pending') return 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
  return 'bg-muted text-muted-foreground'
}

function StatusTag({ status }: { status: SmsSendStatus }) {
  const { locale } = useLocaleStore()
  return (
    <span className={cn('rounded-md px-2 py-1 text-[11px]', statusTone(status))}>
      {t(`sms.sendStatus.${status}`, locale)}
    </span>
  )
}

export default function SmsSendRecordsPage() {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const canViewCall = hasAnyPermission(user, ['call.record.view'])

  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [status, setStatus] = useState<SmsSendStatus | ''>('')
  const [source, setSource] = useState<SmsSendSource | ''>('')
  const [openId, setOpenId] = useState<number | null>(null)
  const [openCallId, setOpenCallId] = useState<string | null>(null)

  const params = useMemo(
    () => ({
      page,
      per_page: perPage,
      q: keyword || undefined,
      status: status || undefined,
      source: source || undefined,
    }),
    [page, perPage, keyword, status, source],
  )
  const { data, isLoading } = useSmsSendRecords(params)
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  return (
    <div className="flex h-full min-w-0 flex-col">
      {/* Filters */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 px-6 py-4">
        <div className="relative">
          <IconSearch
            size={14}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            placeholder={t('sms.records.searchPlaceholder', locale)}
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setKeyword(keywordInput.trim())
                setPage(1)
              }
            }}
            className="h-9 w-[240px] rounded-md border border-border bg-white pl-7 pr-2 text-sm"
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as SmsSendStatus | '')
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-white px-2 text-sm"
        >
          <option value="">{t('sms.records.statusAll', locale)}</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{t(`sms.sendStatus.${s}`, locale)}</option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => {
            setSource(e.target.value as SmsSendSource | '')
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-white px-2 text-sm"
        >
          <option value="">{t('sms.records.sourceAll', locale)}</option>
          {SOURCE_OPTIONS.map((s) => (
            <option key={s} value={s}>{t(`sms.sendSource.${s}`, locale)}</option>
          ))}
        </select>
        {(keyword || status || source) && (
          <button
            type="button"
            onClick={() => {
              setKeyword('')
              setKeywordInput('')
              setStatus('')
              setSource('')
              setPage(1)
            }}
            className="text-xs text-muted-foreground underline"
          >
            {t('sms.records.reset', locale)}
          </button>
        )}
      </div>

      {/* Table */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pt-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-background">
          <div className="min-h-0 flex-1 overflow-auto">
            {isLoading ? (
              <div className="flex h-full min-h-[200px] items-center justify-center">
                <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex h-full min-h-[200px] items-center justify-center px-4">
                <p className="text-sm text-muted-foreground">{t('sms.records.empty', locale)}</p>
              </div>
            ) : (
              <table className="w-max min-w-full border-separate border-spacing-0 table-auto">
                <thead>
                  <tr>
                    <th className="sticky top-0 z-10 w-[150px] rounded-tl-lg border-b border-border bg-muted py-3 pl-4 pr-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.phone', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[180px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.template', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[130px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.sign', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[110px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.status', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[110px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.source', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[130px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.sender', locale)}
                    </th>
                    <th className="sticky top-0 z-10 w-[140px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.call', locale)}
                    </th>
                    <th className="sticky top-0 z-10 min-w-[190px] whitespace-nowrap rounded-tr-lg border-b border-border bg-muted py-3 pl-3 pr-4 text-left text-xs font-semibold text-muted-foreground">
                      {t('sms.records.col.time', locale)}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r: SmsSendRecordItem) => (
                    <tr
                      key={r.id}
                      onClick={() => setOpenId(r.id)}
                      className="cursor-pointer transition-colors hover:bg-accent/30"
                    >
                      <td className="border-b border-border py-3 pl-4 pr-3 font-mono text-sm text-foreground">
                        {r.phone}
                      </td>
                      <td className="max-w-[180px] truncate border-b border-border px-3 py-3 text-sm text-foreground">
                        {r.template_name}
                      </td>
                      <td className="max-w-[130px] truncate border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {r.sign_name}
                      </td>
                      <td className="border-b border-border px-3 py-3">
                        <StatusTag status={r.status} />
                      </td>
                      <td className="border-b border-border px-3 py-3 text-sm">
                        {r.source === 'bulk' && r.bulk_task_id ? (
                          <Link
                            href={`/workspace/engagement/sms-tasks/${r.bulk_task_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sky-700 underline-offset-2 hover:underline dark:text-sky-400"
                          >
                            {t('sms.sendSource.bulk', locale)}
                          </Link>
                        ) : (
                          <span className="text-muted-foreground">{t(`sms.sendSource.${r.source}`, locale)}</span>
                        )}
                      </td>
                      <td className="max-w-[130px] truncate border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {r.employee_name || '—'}
                      </td>
                      <td className="border-b border-border px-3 py-3 text-sm">
                        {r.call_record_public_id && r.call_id ? (
                          canViewCall ? (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                setOpenCallId(r.call_record_public_id)
                              }}
                              className="text-sky-700 underline-offset-2 hover:underline dark:text-sky-400"
                            >
                              {r.call_id}
                            </button>
                          ) : (
                            <span className="text-muted-foreground">{r.call_id}</span>
                          )
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="min-w-[190px] whitespace-nowrap border-b border-border py-3 pl-3 pr-4 text-sm text-muted-foreground">
                        {fmtDate(r.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex shrink-0 items-center justify-between px-6 py-3">
          <span className="text-xs text-muted-foreground">
            {t('sms.records.pagination.total', locale).replace('{total}', String(total))}
          </span>
          <div className="flex items-center gap-2">
            <select
              value={perPage}
              onChange={(e) => {
                setPage(1)
                setPerPage(Number(e.target.value))
              }}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs outline-none"
            >
              {PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {t('sms.records.pagination.perPage', locale).replace('{n}', String(n))}
                </option>
              ))}
            </select>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
                let pageNum: number
                if (pages <= 7) {
                  pageNum = i + 1
                } else if (page <= 4) {
                  pageNum = i + 1
                } else if (page >= pages - 3) {
                  pageNum = pages - 6 + i
                } else {
                  pageNum = page - 3 + i
                }
                return (
                  <button
                    key={pageNum}
                    type="button"
                    onClick={() => setPage(pageNum)}
                    className={cn(
                      'flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs transition-colors',
                      page === pageNum
                        ? 'bg-primary text-primary-foreground'
                        : 'border border-border text-foreground hover:bg-accent',
                    )}
                  >
                    {pageNum}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {openId !== null && (
        <SmsRecordDetailDrawer recordId={openId} onClose={() => setOpenId(null)} />
      )}
      {openCallId !== null && (
        <CallRecordDetailDrawer recordId={openCallId} onClose={() => setOpenCallId(null)} />
      )}
    </div>
  )
}

function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}

function SmsRecordDetailDrawer({ recordId, onClose }: { recordId: number; onClose: () => void }) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSmsSendRecord(recordId)

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-[440px] flex-col border-l border-border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">{t('sms.records.detail.title', locale)}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('sms.records.detail.close', locale)}
            className="text-muted-foreground hover:text-foreground"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {isLoading || !data ? (
            <div className="flex h-full min-h-[200px] items-center justify-center">
              <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-5 text-sm">
              <DetailField label={t('sms.records.detail.phone', locale)}>
                <div className="font-mono font-medium">{data.phone}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.template', locale)}>
                <div className="font-medium">{data.template_name}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.sign', locale)}>
                <div className="font-medium">{data.sign_name}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.status', locale)}>
                <StatusTag status={data.status} />
              </DetailField>
              {data.fail_reason ? (
                <DetailField label={t('sms.records.detail.failReason', locale)}>
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                    {data.fail_reason}
                  </div>
                </DetailField>
              ) : null}
              <DetailField label={t('sms.records.detail.body', locale)}>
                <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 leading-6">
                  {data.body_snapshot}
                </div>
              </DetailField>
              <DetailField label={t('sms.records.detail.source', locale)}>
                {data.source === 'bulk' && data.bulk_task_id ? (
                  <Link
                    href={`/workspace/engagement/sms-tasks/${data.bulk_task_id}`}
                    className="font-medium text-sky-700 underline-offset-2 hover:underline dark:text-sky-400"
                  >
                    {t('sms.records.detail.sourceBulkLink', locale)}
                  </Link>
                ) : (
                  <div className="font-medium">{t(`sms.sendSource.${data.source}`, locale)}</div>
                )}
              </DetailField>
              <DetailField label={t('sms.records.detail.sender', locale)}>
                <div className="font-medium">{data.employee_name || '—'}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.call', locale)}>
                <div className="font-medium">{data.call_id ?? '—'}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.time', locale)}>
                <div className="font-medium">{fmtDate(data.created_at)}</div>
              </DetailField>
              <DetailField label={t('sms.records.detail.providerBizId', locale)}>
                <div className="font-mono text-xs">{data.provider_biz_id ?? '—'}</div>
              </DetailField>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
