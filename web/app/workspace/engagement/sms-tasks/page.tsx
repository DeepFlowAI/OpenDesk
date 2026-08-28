'use client'

import Link from 'next/link'
import { useState } from 'react'
import { IconEye, IconPlus, IconSearch } from '@tabler/icons-react'
import {
  EmptyState,
  formatDateTime,
  formatPercent,
  SmsTaskStatusBadge,
} from '@/app/components/features/engagement/sms-bulk-task-ui'
import { useAuthStore } from '@/context/auth-store'
import { hasAnyPermission } from '@/utils/permissions'
import { cn } from '@/lib/utils'
import { useSmsBulkTasks } from '@/service/use-sms-bulk-tasks'
import type { SmsBulkTaskStatus } from '@/models/sms-bulk-task'

const PER_PAGE_OPTIONS = [20, 50, 100]
const STATUS_OPTIONS: SmsBulkTaskStatus[] = ['draft', 'scheduled', 'sending', 'paused', 'completed', 'archived']
const STATUS_FILTER_LABELS: Record<SmsBulkTaskStatus, string> = {
  draft: '草稿',
  scheduled: '待发送',
  sending: '发送中',
  paused: '已暂停',
  completed: '已完成',
  archived: '已归档',
}

export default function SmsBulkTaskListPage() {
  const user = useAuthStore((state) => state.user)
  const canCreate = hasAnyPermission(user, ['engagement.sms_task.manage', 'engagement.sms_task.create'])
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [status, setStatus] = useState<SmsBulkTaskStatus | ''>('')
  const { data, isLoading } = useSmsBulkTasks({
    page,
    per_page: perPage,
    q: keyword || undefined,
    status: status || undefined,
  })
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">短信群发任务</h1>
          <p className="mt-1 text-sm text-muted-foreground">批量发送营销与通知短信，跟踪送达效果</p>
        </div>
        {canCreate && (
          <Link
            href="/workspace/engagement/sms-tasks/new"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <IconPlus size={16} />
            新建任务
          </Link>
        )}
      </header>

      <div className="flex shrink-0 items-center gap-3 px-6 py-4">
        <div className="relative">
          <IconSearch size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索任务名称"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setKeyword(keywordInput.trim())
                setPage(1)
              }
            }}
            className="h-9 w-[240px] rounded-md border border-border bg-background pl-7 pr-2 text-sm outline-none"
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as SmsBulkTaskStatus | '')
            setPage(1)
          }}
          className="h-9 rounded-md border border-border bg-background px-2 text-sm"
        >
          <option value="">全部状态</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{STATUS_FILTER_LABELS[s]}</option>
          ))}
        </select>
        {(keyword || status) && (
          <button
            type="button"
            onClick={() => {
              setKeyword('')
              setKeywordInput('')
              setStatus('')
              setPage(1)
            }}
            className="text-xs text-muted-foreground underline"
          >
            重置
          </button>
        )}
      </div>

      <main className="min-h-0 flex-1 overflow-auto px-6 pb-6">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : items.length === 0 ? (
          <EmptyState
            title={keyword || status ? '没有符合条件的任务' : '暂无短信群发任务'}
            action={
              canCreate && !keyword && !status ? (
                <Link
                  href="/workspace/engagement/sms-tasks/new"
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
                >
                  <IconPlus size={16} />
                  新建任务
                </Link>
              ) : undefined
            }
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted text-left text-xs font-semibold text-muted-foreground">
                  <th className="px-4 py-3">任务名称</th>
                  <th className="px-3 py-3">短信模板</th>
                  <th className="px-3 py-3">状态</th>
                  <th className="px-3 py-3">发送进度</th>
                  <th className="px-3 py-3">送达率</th>
                  <th className="px-3 py-3">发送时间</th>
                  <th className="px-3 py-3">创建人</th>
                  <th className="px-3 py-3">更新时间</th>
                  <th className="px-3 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((task) => {
                  const finished = task.stats.delivered + task.stats.failed
                  const progress = task.stats.total > 0 ? Math.round((finished / task.stats.total) * 100) : 0
                  return (
                    <tr key={task.id} className="border-b border-border last:border-0 hover:bg-accent/30">
                      <td className="max-w-[220px] px-4 py-3">
                        <Link
                          href={`/workspace/engagement/sms-tasks/${task.id}`}
                          className="block truncate font-medium text-foreground hover:text-primary"
                        >
                          {task.name}
                        </Link>
                      </td>
                      <td className="max-w-[160px] truncate px-3 py-3 text-muted-foreground">{task.template_name}</td>
                      <td className="px-3 py-3"><SmsTaskStatusBadge status={task.status} /></td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-primary" style={{ width: `${progress}%` }} />
                          </div>
                          <span className="text-xs text-muted-foreground">{finished}/{task.stats.total}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">
                        {formatPercent(task.stats.delivered, task.stats.delivered + task.stats.failed)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-muted-foreground">
                        {task.send_type === 'immediate' ? '立即发送' : formatDateTime(task.scheduled_at)}
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">{task.created_by_name || '-'}</td>
                      <td className="whitespace-nowrap px-3 py-3 text-muted-foreground">{formatDateTime(task.updated_at)}</td>
                      <td className="px-3 py-3 text-right">
                        <Link
                          href={`/workspace/engagement/sms-tasks/${task.id}`}
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-accent"
                        >
                          <IconEye size={14} />
                          查看
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {total > 0 && (
        <div className="flex shrink-0 items-center justify-between border-t border-border px-6 py-3">
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
                <option key={n} value={n}>{n} 条/页</option>
              ))}
            </select>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
                let pageNum: number
                if (pages <= 7) pageNum = i + 1
                else if (page <= 4) pageNum = i + 1
                else if (page >= pages - 3) pageNum = pages - 6 + i
                else pageNum = page - 3 + i
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
    </div>
  )
}
