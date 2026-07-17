'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { IconArchive, IconEdit, IconEye, IconPlayerPause, IconPlayerPlay, IconPlus, IconSearch } from '@tabler/icons-react'
import { toast } from 'sonner'
import { EmptyState, formatDateTime, formatPercent, TaskStatusBadge } from '@/app/components/features/engagement/outbound-task-ui'
import { useAuthStore } from '@/context/auth-store'
import { OUTBOUND_TASK_STATUS_LABELS, type OutboundTaskStatus } from '@/models/outbound-task'
import { useOutboundTasks, useTransitionOutboundTask } from '@/service/use-outbound-tasks'
import { hasPermission } from '@/utils/permissions'

const statusOptions: Array<{ value: '' | OutboundTaskStatus; label: string }> = [
  { value: '', label: '全部状态' },
  ...Object.entries(OUTBOUND_TASK_STATUS_LABELS).map(([value, label]) => ({ value: value as OutboundTaskStatus, label })),
]

export default function OutboundTasksPage() {
  const user = useAuthStore((state) => state.user)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<'' | OutboundTaskStatus>('')
  const params = useMemo(() => ({ page: 1, per_page: 50, q, status }), [q, status])
  const { data, isLoading } = useOutboundTasks(params)
  const transition = useTransitionOutboundTask()
  const canCreate = hasPermission(user, 'engagement.outbound_task.create')

  const runAction = async (id: number, action: 'pause' | 'resume' | 'archive') => {
    try {
      await transition.mutateAsync({ id, action })
      toast.success('操作成功')
    } catch {
      toast.error('操作失败，请重试')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">人工外呼任务</h1>
          <p className="mt-1 text-sm text-muted-foreground">创建、分配并跟踪人工外呼对象</p>
        </div>
        {canCreate && (
          <Link href="/workspace/engagement/outbound-tasks/new" className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
            <IconPlus size={16} />
            新建任务
          </Link>
        )}
      </header>

      <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3">
        <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索任务名称" className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value as '' | OutboundTaskStatus)} className="h-9 rounded-md border border-border bg-background px-3 text-sm">
          {statusOptions.map((option) => (
            <option key={option.value || 'all'} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title={q || status ? '未找到符合条件的外呼任务' : '暂无外呼任务'}
            action={canCreate && !q && !status ? <Link href="/workspace/engagement/outbound-tasks/new" className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">新建任务</Link> : null}
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">任务名称</th>
                  <th className="px-4 py-3 font-medium">模板</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">进度</th>
                  <th className="px-4 py-3 font-medium">接通率</th>
                  <th className="px-4 py-3 font-medium">截止时间</th>
                  <th className="px-4 py-3 font-medium">更新时间</th>
                  <th className="w-36 px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((task) => (
                  <tr key={task.id} className="border-t border-border">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/workspace/engagement/outbound-tasks/${task.id}`} className="hover:underline">{task.name}</Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{task.template_name}</td>
                    <td className="px-4 py-3"><TaskStatusBadge status={task.status} /></td>
                    <td className="px-4 py-3">{task.stats.completed_targets} / {task.stats.total_targets}</td>
                    <td className="px-4 py-3">{formatPercent(task.stats.answered_count, task.stats.call_count)}</td>
                    <td className="px-4 py-3">{formatDateTime(task.due_at)}</td>
                    <td className="px-4 py-3">{formatDateTime(task.updated_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link title="查看" href={`/workspace/engagement/outbound-tasks/${task.id}`}><IconEye size={17} /></Link>
                        {task.status === 'draft' || task.status === 'paused' ? (
                          <Link title="编辑" href={`/workspace/engagement/outbound-tasks/${task.id}`}><IconEdit size={17} /></Link>
                        ) : null}
                        {task.status === 'active' && <button title="暂停" onClick={() => void runAction(task.id, 'pause')}><IconPlayerPause size={17} /></button>}
                        {task.status === 'paused' && <button title="恢复" onClick={() => void runAction(task.id, 'resume')}><IconPlayerPlay size={17} /></button>}
                        {(task.status === 'paused' || task.status === 'completed') && <button title="归档" onClick={() => void runAction(task.id, 'archive')}><IconArchive size={17} /></button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  )
}
