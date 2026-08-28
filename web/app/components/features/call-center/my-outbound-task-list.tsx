'use client'

import { IconChevronRight } from '@tabler/icons-react'

import { EmptyState, formatDateTime } from '@/app/components/features/engagement/outbound-task-ui'
import { useLocaleStore } from '@/context/locale-store'
import type { MyOutboundTaskItem } from '@/models/outbound-task'
import { useMyOutboundTasks } from '@/service/use-outbound-tasks'
import { t } from '@/utils/i18n'
import { ExecTaskStatusBadge } from './my-outbound-badges'

function taskProgressPercent(task: MyOutboundTaskItem): number {
  if (!task.my_total) return 0
  return Math.round((task.my_completed / task.my_total) * 100)
}

function isOverdue(dueAt: string | null): boolean {
  return Boolean(dueAt) && new Date(dueAt!).getTime() < Date.now()
}

export function MyOutboundTaskList({ onOpenTask }: { onOpenTask: (taskId: number) => void }) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useMyOutboundTasks()
  const items = data?.items ?? []

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-muted/40">
      <div className="border-b border-border bg-background px-6 py-4">
        <h1 className="text-base font-semibold">{t('ws.outboundExec.list.title', locale)}</h1>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-5">
        {isLoading ? (
          <p className="p-2 text-sm text-muted-foreground">{t('ws.outboundExec.list.loading', locale)}</p>
        ) : items.length === 0 ? (
          <EmptyState title={t('ws.outboundExec.list.empty', locale)} />
        ) : (
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/60 text-xs">
                  <th className="px-5 py-3 font-medium text-muted-foreground">{t('ws.outboundExec.list.col.task', locale)}</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">{t('ws.outboundExec.list.col.status', locale)}</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">{t('ws.outboundExec.list.col.progress', locale)}</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">{t('ws.outboundExec.list.col.dueAt', locale)}</th>
                  <th className="px-5 py-3 text-right font-medium text-muted-foreground">{t('ws.outboundExec.list.col.action', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((task) => {
                  const pct = taskProgressPercent(task)
                  const overdue = isOverdue(task.due_at)
                  return (
                    <tr key={task.id} className="border-b border-border/50 last:border-0">
                      <td className="px-5 py-3.5 font-medium">{task.name}</td>
                      <td className="px-4 py-3.5">
                        <ExecTaskStatusBadge status={task.status} />
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {task.my_completed}/{task.my_total} · {pct}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 text-xs">
                        <span className={overdue ? 'font-medium text-destructive' : 'text-muted-foreground'}>
                          {overdue ? `${t('ws.outboundExec.list.overdue', locale)} · ` : ''}
                          {formatDateTime(task.due_at)}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <button
                          type="button"
                          onClick={() => onOpenTask(task.id)}
                          className="inline-flex h-8 items-center gap-1 rounded-lg border border-border bg-background px-3 text-xs font-medium hover:bg-muted"
                        >
                          {t('ws.outboundExec.list.view', locale)}
                          <IconChevronRight size={13} />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
