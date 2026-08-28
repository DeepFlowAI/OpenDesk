'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import { useLocaleStore } from '@/context/locale-store'
import type { OutboundTarget } from '@/models/outbound-task'
import { useMyOutboundTasks } from '@/service/use-outbound-tasks'
import { t } from '@/utils/i18n'
import { MyOutboundExecPage } from './my-outbound-exec-page'
import { MyOutboundTaskList } from './my-outbound-task-list'

export function MyOutboundTargetsView({
  taskId,
  onStartCall,
  onOpenScreenPop,
}: {
  taskId: number | null
  onStartCall?: (phone: string, taskId: number) => void | Promise<void>
  onOpenScreenPop?: (target: OutboundTarget) => void
}) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const myTasksQuery = useMyOutboundTasks()
  const task = taskId == null ? null : (myTasksQuery.data?.items.find((item) => item.id === taskId) ?? null)
  const invalidToastShownRef = useRef<number | null>(null)

  // A taskId that is not in the agent's visible task list (paused, archived,
  // or reassigned) falls back to the task list instead of rendering a stale page.
  useEffect(() => {
    if (taskId == null || myTasksQuery.isLoading || myTasksQuery.isError) return
    if (task) return
    if (invalidToastShownRef.current === taskId) return
    invalidToastShownRef.current = taskId
    toast.error(t('ws.outboundExec.exec.taskChanged', locale))
    router.replace('/workspace/call?view=outbound-tasks')
  }, [taskId, task, myTasksQuery.isLoading, myTasksQuery.isError, locale, router])

  if (taskId == null) {
    return (
      <MyOutboundTaskList
        onOpenTask={(id) => router.push(`/workspace/call?view=outbound-tasks&taskId=${id}`)}
      />
    )
  }

  if (!task) {
    return <div className="h-full bg-muted/40" />
  }

  return (
    <MyOutboundExecPage
      task={task}
      onBack={() => router.push('/workspace/call?view=outbound-tasks')}
      onStartCall={onStartCall}
      onOpenScreenPop={onOpenScreenPop}
    />
  )
}
