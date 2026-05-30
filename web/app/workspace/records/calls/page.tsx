'use client'
/**
 * Call records page — list + filters + detail drawer.
 */
import { useMemo, useState } from 'react'
import {
  IconLoader2,
  IconPhoneIncoming,
  IconPhoneOutgoing,
  IconSearch,
} from '@tabler/icons-react'

import { useCallRecords } from '@/service/use-call-center'
import type { CallRecordListItem } from '@/models/call-center'
import { CallRecordDetailDrawer } from '@/app/components/features/call-center/call-record-detail-drawer'
import { cn } from '@/lib/utils'

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—'
  const s = Math.floor(ms / 1000)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function customerNumber(record: Pick<CallRecordListItem, 'direction' | 'from_number' | 'to_number'>): string | null {
  return record.direction === 'outbound' ? record.to_number : record.from_number
}

function serviceNumber(record: Pick<CallRecordListItem, 'direction' | 'from_number' | 'to_number'>): string | null {
  return record.direction === 'outbound' ? record.from_number : record.to_number
}

function associatedUserLabel(record: Pick<CallRecordListItem, 'user_name' | 'user_public_id'>): string | null {
  return record.user_name || record.user_public_id
}

function associationStatusLabel(status: CallRecordListItem['user_association_status']): string {
  switch (status) {
    case 'linked':
      return '已关联'
    case 'created':
      return '已新建'
    case 'multiple':
      return '待选择'
    case 'unknown':
      return '未知号码'
    case 'failed':
      return '识别失败'
    default:
      return '待匹配'
  }
}

const PER_PAGE_OPTIONS = [20, 50, 100]

export default function CallRecordsPage() {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [direction, setDirection] = useState<'all' | 'inbound' | 'outbound'>('all')
  const [keyword, setKeyword] = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [openId, setOpenId] = useState<number | null>(null)

  const params = useMemo(
    () => ({
      page,
      per_page: perPage,
      direction: direction === 'all' ? undefined : direction,
      keyword: keyword || undefined,
    }),
    [page, perPage, direction, keyword],
  )
  const { data, isLoading } = useCallRecords(params)
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  return (
    <div className="flex h-full min-w-0 flex-col">
      {/* Filters */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 px-6 py-4">
        <select
          value={direction}
          onChange={(e) => {
            setDirection(e.target.value as 'all' | 'inbound' | 'outbound')
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-white px-2 text-sm"
        >
          <option value="all">全部类型</option>
          <option value="inbound">呼入</option>
          <option value="outbound">呼出</option>
        </select>
        <div className="relative">
          <IconSearch
            size={14}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            placeholder="搜索号码或通话 ID"
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
        {keyword && (
          <button
            type="button"
            onClick={() => {
              setKeyword('')
              setKeywordInput('')
              setPage(1)
            }}
            className="text-xs text-muted-foreground underline"
          >
            清除筛选
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
                <p className="text-sm text-muted-foreground">暂无通话记录</p>
              </div>
            ) : (
              <table className="w-max min-w-full border-separate border-spacing-0 table-auto">
                <thead>
                  <tr>
                    <th className="sticky top-0 z-10 w-[170px] rounded-tl-lg border-b border-border bg-muted py-3 pl-4 pr-3 text-left text-xs font-semibold text-muted-foreground">
                      用户号码
                    </th>
                    <th className="sticky top-0 z-10 w-[100px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      通话类型
                    </th>
                    <th className="sticky top-0 z-10 w-[180px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      关联用户
                    </th>
                    <th className="sticky top-0 z-10 w-[170px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      服务号码
                    </th>
                    <th className="sticky top-0 z-10 w-[140px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      接待客服
                    </th>
                    <th className="sticky top-0 z-10 min-w-[190px] whitespace-nowrap border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      开始时间
                    </th>
                    <th className="sticky top-0 z-10 w-[120px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                      通话时长
                    </th>
                    <th className="sticky top-0 z-10 w-[140px] rounded-tr-lg border-b border-border bg-muted py-3 pl-3 pr-4 text-left text-xs font-semibold text-muted-foreground">
                      状态
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r: CallRecordListItem) => (
                    <tr
                      key={r.id}
                      onClick={() => setOpenId(r.id)}
                      className="cursor-pointer transition-colors hover:bg-accent/30"
                    >
                      <td className="max-w-[170px] truncate border-b border-border py-3 pl-4 pr-3 text-sm text-foreground">
                        {customerNumber(r) || '未知号码'}
                      </td>
                      <td className="border-b border-border px-3 py-3">
                        {r.direction === 'inbound' ? (
                          <span className="inline-flex items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                            <IconPhoneIncoming size={10} /> 呼入
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700">
                            <IconPhoneOutgoing size={10} /> 呼出
                          </span>
                        )}
                      </td>
                      <td className="max-w-[180px] border-b border-border px-3 py-3">
                        <AssociatedUserInline record={r} />
                      </td>
                      <td className="max-w-[170px] truncate border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {serviceNumber(r) || '—'}
                      </td>
                      <td className="max-w-[140px] truncate border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {r.agent_name || '—'}
                      </td>
                      <td className="min-w-[190px] whitespace-nowrap border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {fmtDate(r.started_at)}
                      </td>
                      <td className="border-b border-border px-3 py-3 text-sm text-muted-foreground">
                        {fmtDuration(r.talk_duration_ms)}
                      </td>
                      <td className="border-b border-border py-3 pl-3 pr-4 text-xs text-muted-foreground">
                        {r.state}
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
          <span className="text-xs text-muted-foreground">共 {total} 条</span>
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
                <option key={n} value={n}>{n} / page</option>
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
        <CallRecordDetailDrawer recordId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}

function AssociatedUserInline({ record }: { record: CallRecordListItem }) {
  const label = associatedUserLabel(record)

  if (!label) {
    return (
      <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
        {associationStatusLabel(record.user_association_status)}
      </span>
    )
  }

  return (
    <div className="min-w-0">
      <div className="truncate text-sm text-foreground">{label}</div>
    </div>
  )
}
