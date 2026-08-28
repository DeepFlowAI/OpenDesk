'use client'

import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  IconArrowLeft,
  IconArchive,
  IconEdit,
  IconLoader2,
  IconPlayerPause,
  IconPlayerPlay,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconSend,
  IconTrash,
  IconUpload,
} from '@tabler/icons-react'
import {
  formatDateTime,
  formatPercent,
  renderSmsBody,
  SmsTargetStatusBadge,
  SmsTaskStatusBadge,
} from '@/app/components/features/engagement/sms-bulk-task-ui'
import { SmsTaskImportDialog } from '@/app/components/features/engagement/sms-task-import-dialog'
import {
  SmsTaskTargetAddDialog,
  SmsTaskTargetDetailDrawer,
} from '@/app/components/features/engagement/sms-task-target-dialogs'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useAuthStore } from '@/context/auth-store'
import { hasAnyPermission } from '@/utils/permissions'
import { cn } from '@/lib/utils'
import {
  useBulkDeleteSmsBulkTargets,
  useDeleteSmsBulkTask,
  useResendFailedSmsBulkTargets,
  useSmsBulkAvailableTemplates,
  useSmsBulkTargets,
  useSmsBulkTask,
  useTransitionSmsBulkTask,
  useUpdateSmsBulkTask,
} from '@/service/use-sms-bulk-tasks'
import type { SmsBulkSendType, SmsBulkTargetStatus } from '@/models/sms-bulk-task'

type DetailTab = 'targets' | 'info'
type ConfirmAction = 'publish' | 'pause' | 'resume' | 'archive' | 'delete' | 'resend' | 'bulkDelete' | 'switchTemplate' | null

const PER_PAGE_OPTIONS = [20, 50, 100]
const TARGET_STATUS_OPTIONS: SmsBulkTargetStatus[] = ['pending', 'sending', 'submitted', 'delivered', 'failed']
const TARGET_STATUS_LABELS: Record<SmsBulkTargetStatus, string> = {
  pending: '待发送',
  sending: '发送中',
  submitted: '已提交',
  delivered: '送达成功',
  failed: '发送失败',
}

export default function SmsBulkTaskDetailPage() {
  const params = useParams()
  const router = useRouter()
  const taskId = Number(params.taskId)
  const user = useAuthStore((state) => state.user)

  const [activeTab, setActiveTab] = useState<DetailTab>('targets')
  const [editing, setEditing] = useState(false)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [openTargetId, setOpenTargetId] = useState<number | null>(null)
  const [selectedTargetIds, setSelectedTargetIds] = useState<number[]>([])
  const [targetPage, setTargetPage] = useState(1)
  const [targetPerPage, setTargetPerPage] = useState(20)
  const [targetKeyword, setTargetKeyword] = useState('')
  const [targetKeywordInput, setTargetKeywordInput] = useState('')
  const [targetStatus, setTargetStatus] = useState<SmsBulkTargetStatus | ''>('')

  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editTemplateId, setEditTemplateId] = useState(0)
  const [editSendType, setEditSendType] = useState<SmsBulkSendType>('immediate')
  const [editScheduledAt, setEditScheduledAt] = useState('')

  const { data: task, isLoading } = useSmsBulkTask(taskId)
  const { data: targetsData } = useSmsBulkTargets(taskId, {
    page: targetPage,
    per_page: targetPerPage,
    q: targetKeyword || undefined,
    status: targetStatus || undefined,
  })
  const { data: templates } = useSmsBulkAvailableTemplates({ enabled: editing })
  const transition = useTransitionSmsBulkTask()
  const deleteTask = useDeleteSmsBulkTask()
  const updateTask = useUpdateSmsBulkTask()
  const bulkDelete = useBulkDeleteSmsBulkTargets(taskId)
  const resendFailed = useResendFailedSmsBulkTargets(taskId)

  const targets = targetsData?.items ?? []
  const targetTotal = targetsData?.total ?? 0
  const targetPages = targetsData?.pages ?? 0

  const canManage = useMemo(() => {
    if (!user || !task) return false
    if (hasAnyPermission(user, ['engagement.sms_task.manage'])) return true
    return hasAnyPermission(user, ['engagement.sms_task.create']) && task.created_by_id === user.id
  }, [user, task])

  const templateForRender = useMemo(() => {
    if (!task) return null
    return {
      id: task.template_id ?? 0,
      name: task.template_name,
      sign_name: task.sign_name,
      type: task.template_type,
      variables: task.variables,
      body: task.body,
    }
  }, [task])

  const editable = task ? ['draft', 'scheduled', 'paused'].includes(task.status) : false

  const startEditing = () => {
    if (!task) return
    setEditName(task.name)
    setEditDescription(task.description ?? '')
    setEditTemplateId(task.template_id ?? 0)
    setEditSendType(task.send_type)
    setEditScheduledAt(task.scheduled_at ? toLocalInputValue(task.scheduled_at) : '')
    setEditing(true)
  }

  const handleSaveEdit = async () => {
    if (!task) return
    if (!editName.trim()) {
      toast.error('请输入任务名称')
      return
    }
    if (editSendType === 'scheduled') {
      if (!editScheduledAt) {
        toast.error('请选择定时发送时间')
        return
      }
      if (new Date(editScheduledAt).getTime() <= Date.now()) {
        toast.error('定时发送时间需晚于当前时间')
        return
      }
    }
    const switchingTemplate = task.status === 'draft' && editTemplateId > 0 && editTemplateId !== task.template_id
    if (switchingTemplate && task.stats.total > 0) {
      setConfirmAction('switchTemplate')
      return
    }
    await submitEdit(switchingTemplate)
  }

  const submitEdit = async (switchingTemplate: boolean) => {
    if (!task) return
    try {
      await updateTask.mutateAsync({
        id: taskId,
        data: {
          name: editName.trim(),
          description: editDescription.trim() || null,
          ...(switchingTemplate ? { template_id: editTemplateId } : {}),
          send_type: editSendType,
          scheduled_at: editSendType === 'scheduled' ? new Date(editScheduledAt).toISOString() : null,
        },
      })
      toast.success('任务已更新')
      setEditing(false)
      setConfirmAction(null)
    } catch {
      toast.error('保存失败，请重试')
    }
  }

  const handleConfirm = async () => {
    if (!task || !confirmAction) return
    try {
      if (confirmAction === 'switchTemplate') {
        await submitEdit(true)
        return
      }
      if (confirmAction === 'delete') {
        await deleteTask.mutateAsync(taskId)
        toast.success('任务已删除')
        router.push('/workspace/engagement/sms-tasks')
        return
      }
      if (confirmAction === 'resend') {
        const result = await resendFailed.mutateAsync()
        toast.success(result.reset > 0 ? `已重置 ${result.reset} 个失败对象，将重新发送` : '当前没有失败对象')
        setConfirmAction(null)
        return
      }
      if (confirmAction === 'bulkDelete') {
        const result = await bulkDelete.mutateAsync(selectedTargetIds)
        toast.success(
          result.skipped > 0
            ? `已删除 ${result.deleted} 个对象，${result.skipped} 个非待发送对象被跳过`
            : `已删除 ${result.deleted} 个对象`,
        )
        setSelectedTargetIds([])
        setConfirmAction(null)
        return
      }
      await transition.mutateAsync({ id: taskId, action: confirmAction })
      const messages = { publish: '任务已发布', pause: '任务已暂停', resume: '任务已恢复', archive: '任务已归档' } as const
      toast.success(messages[confirmAction])
      setConfirmAction(null)
    } catch (error) {
      const detail = (error as { response?: { json?: () => Promise<{ detail?: string }> } })?.response
      let message = '操作失败，请重试'
      if (detail?.json) {
        try {
          const body = await detail.json()
          if (typeof body?.detail === 'string') message = body.detail
        } catch { /* keep default */ }
      }
      toast.error(message)
      setConfirmAction(null)
    }
  }

  if (isLoading || !task) {
    return (
      <div className="flex h-full items-center justify-center">
        <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    )
  }

  const stats = task.stats
  const finished = stats.delivered + stats.failed
  const pendingTemplate = editing && templates?.items.find((t) => t.id === editTemplateId)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/workspace/engagement/sms-tasks" className="rounded-md p-2 hover:bg-muted">
              <IconArrowLeft size={18} />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-foreground">{task.name}</h1>
                <SmsTaskStatusBadge status={task.status} />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {task.template_name} · {task.sign_name} ·{' '}
                {task.send_type === 'immediate' ? '立即发送' : `定时 ${formatDateTime(task.scheduled_at)}`} ·
                创建于 {formatDateTime(task.created_at)}
              </p>
            </div>
          </div>
          {canManage && !editing && (
            <div className="flex items-center gap-2">
              {editable && (
                <button type="button" onClick={startEditing} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                  <IconEdit size={15} /> 编辑
                </button>
              )}
              {task.status === 'draft' && (
                <>
                  <button type="button" onClick={() => setConfirmAction('publish')} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
                    <IconSend size={15} /> 发布
                  </button>
                  <button type="button" onClick={() => setConfirmAction('delete')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm text-destructive hover:bg-destructive/10">
                    <IconTrash size={15} /> 删除
                  </button>
                </>
              )}
              {(task.status === 'scheduled' || task.status === 'sending') && (
                <button type="button" onClick={() => setConfirmAction('pause')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                  <IconPlayerPause size={15} /> 暂停
                </button>
              )}
              {task.status === 'paused' && (
                <button type="button" onClick={() => setConfirmAction('resume')} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
                  <IconPlayerPlay size={15} /> 恢复
                </button>
              )}
              {(task.status === 'scheduled' || task.status === 'paused' || task.status === 'completed') && (
                <button type="button" onClick={() => setConfirmAction('archive')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                  <IconArchive size={15} /> 归档
                </button>
              )}
            </div>
          )}
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {editing ? (
          <div className="mx-auto max-w-3xl space-y-6">
            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">基本信息</h2>
              <div className="grid gap-4">
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务名称 <span className="text-destructive">*</span></span>
                  <input value={editName} onChange={(e) => setEditName(e.target.value)} className="h-10 rounded-md border border-border bg-background px-3 outline-none" />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务说明</span>
                  <textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} rows={3} className="rounded-md border border-border bg-background px-3 py-2 outline-none" />
                </label>
              </div>
            </section>

            {task.status === 'draft' && (
              <section className="rounded-lg border border-border p-5">
                <h2 className="mb-4 text-base font-semibold">短信模板</h2>
                <select
                  value={editTemplateId}
                  onChange={(e) => setEditTemplateId(Number(e.target.value))}
                  className="h-10 w-full rounded-md border border-border bg-background px-3"
                >
                  {(templates?.items ?? []).map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}（{template.sign_name}）
                    </option>
                  ))}
                </select>
                {pendingTemplate && (
                  <div className="mt-3 rounded-md border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                    {renderSmsBody(pendingTemplate.body)}
                  </div>
                )}
                {editTemplateId !== (task.template_id ?? 0) && task.stats.total > 0 && (
                  <p className="mt-2 text-xs text-warning">更换模板将清空当前任务下全部发送对象</p>
                )}
              </section>
            )}

            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">发送时间</h2>
              <div className="grid gap-3 text-sm">
                <label className="flex items-center gap-2">
                  <input type="radio" name="edit-send-type" checked={editSendType === 'immediate'} onChange={() => setEditSendType('immediate')} />
                  发布后立即发送
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="edit-send-type" checked={editSendType === 'scheduled'} onChange={() => setEditSendType('scheduled')} />
                  定时发送
                </label>
                {editSendType === 'scheduled' && (
                  <input
                    type="datetime-local"
                    value={editScheduledAt}
                    onChange={(e) => setEditScheduledAt(e.target.value)}
                    className="h-10 w-64 rounded-md border border-border bg-background px-3 outline-none"
                  />
                )}
              </div>
            </section>

            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => setEditing(false)} className="rounded-md border border-border px-4 py-2 text-sm">
                取消
              </button>
              <button
                type="button"
                disabled={updateTask.isPending}
                onClick={() => void handleSaveEdit()}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                保存
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-6 grid grid-cols-6 gap-3">
              <MetricCard label="对象总数" value={stats.total} />
              <MetricCard label="待发送" value={stats.pending} />
              <MetricCard label="已提交" value={stats.submitted} tone="info" />
              <MetricCard label="送达成功" value={stats.delivered} tone="success" />
              <MetricCard label="发送失败" value={stats.failed} tone="destructive" />
              <MetricCard label="送达率" value={formatPercent(stats.delivered, finished)} />
            </div>

            <div className="mb-4 flex items-center gap-1 border-b border-border">
              {(['targets', 'info'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={cn(
                    'border-b-2 px-4 py-2 text-sm transition-colors',
                    activeTab === tab
                      ? 'border-primary font-medium text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {tab === 'targets' ? `发送对象（${stats.total}）` : '任务信息'}
                </button>
              ))}
            </div>

            {activeTab === 'targets' && (
              <div>
                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <div className="relative">
                    <IconSearch size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="搜索号码"
                      value={targetKeywordInput}
                      onChange={(e) => setTargetKeywordInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          setTargetKeyword(targetKeywordInput.trim())
                          setTargetPage(1)
                        }
                      }}
                      className="h-9 w-[200px] rounded-md border border-border bg-background pl-7 pr-2 text-sm outline-none"
                    />
                  </div>
                  <select
                    value={targetStatus}
                    onChange={(e) => {
                      setTargetStatus(e.target.value as SmsBulkTargetStatus | '')
                      setTargetPage(1)
                    }}
                    className="h-9 rounded-md border border-border bg-background px-2 text-sm"
                  >
                    <option value="">全部状态</option>
                    {TARGET_STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>{TARGET_STATUS_LABELS[s]}</option>
                    ))}
                  </select>
                  {canManage && task.status !== 'archived' && (
                    <div className="ml-auto flex items-center gap-2">
                      {task.status === 'draft' && (
                        <>
                          <button type="button" onClick={() => setImportOpen(true)} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                            <IconUpload size={15} /> 导入对象
                          </button>
                          <button type="button" onClick={() => setAddOpen(true)} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                            <IconPlus size={15} /> 添加对象
                          </button>
                        </>
                      )}
                      {stats.failed > 0 && ['sending', 'paused', 'completed'].includes(task.status) && (
                        <button type="button" onClick={() => setConfirmAction('resend')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm hover:bg-accent">
                          <IconRefresh size={15} /> 重发失败对象
                        </button>
                      )}
                      {task.status === 'draft' && selectedTargetIds.length > 0 && (
                        <button type="button" onClick={() => setConfirmAction('bulkDelete')} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-sm text-destructive hover:bg-destructive/10">
                          <IconTrash size={15} /> 批量删除（{selectedTargetIds.length}）
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {targets.length === 0 ? (
                  <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-muted/20 text-sm text-muted-foreground">
                    {targetKeyword || targetStatus ? '没有符合条件的发送对象' : '暂无发送对象，请添加或导入'}
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-lg border border-border">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border bg-muted text-left text-xs font-semibold text-muted-foreground">
                          {task.status === 'draft' && canManage && (
                            <th className="w-10 px-3 py-3">
                              <input
                                type="checkbox"
                                checked={targets.length > 0 && targets.every((t) => selectedTargetIds.includes(t.id))}
                                onChange={(e) =>
                                  setSelectedTargetIds(e.target.checked ? targets.map((t) => t.id) : [])
                                }
                              />
                            </th>
                          )}
                          <th className="px-4 py-3">接收号码</th>
                          <th className="px-3 py-3">变量</th>
                          <th className="px-3 py-3">状态</th>
                          <th className="px-3 py-3">失败原因</th>
                          <th className="px-3 py-3">提交时间</th>
                          <th className="px-3 py-3">送达时间</th>
                          <th className="px-3 py-3 text-right">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targets.map((target) => (
                          <tr key={target.id} className="border-b border-border last:border-0 hover:bg-accent/30">
                            {task.status === 'draft' && canManage && (
                              <td className="px-3 py-3">
                                <input
                                  type="checkbox"
                                  checked={selectedTargetIds.includes(target.id)}
                                  onChange={(e) =>
                                    setSelectedTargetIds((ids) =>
                                      e.target.checked ? [...ids, target.id] : ids.filter((id) => id !== target.id),
                                    )
                                  }
                                />
                              </td>
                            )}
                            <td className="px-4 py-3 font-mono text-sm">{target.phone}</td>
                            <td className="max-w-[200px] truncate px-3 py-3 text-muted-foreground">
                              {Object.entries(target.variable_values)
                                .map(([key, value]) => `${key}=${value}`)
                                .join('，') || '-'}
                            </td>
                            <td className="px-3 py-3"><SmsTargetStatusBadge status={target.status} /></td>
                            <td className="max-w-[160px] truncate px-3 py-3 text-muted-foreground">{target.fail_reason || '-'}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-muted-foreground">{formatDateTime(target.submitted_at)}</td>
                            <td className="whitespace-nowrap px-3 py-3 text-muted-foreground">{formatDateTime(target.delivered_at)}</td>
                            <td className="px-3 py-3 text-right">
                              <button
                                type="button"
                                onClick={() => setOpenTargetId(target.id)}
                                className="rounded-md border border-border px-2 py-1 text-xs hover:bg-accent"
                              >
                                查看
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {targetTotal > 0 && (
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">共 {targetTotal} 条</span>
                    <div className="flex items-center gap-2">
                      <select
                        value={targetPerPage}
                        onChange={(e) => {
                          setTargetPage(1)
                          setTargetPerPage(Number(e.target.value))
                        }}
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs outline-none"
                      >
                        {PER_PAGE_OPTIONS.map((n) => (
                          <option key={n} value={n}>{n} 条/页</option>
                        ))}
                      </select>
                      <div className="flex gap-1">
                        {Array.from({ length: Math.min(targetPages, 7) }, (_, i) => {
                          let pageNum: number
                          if (targetPages <= 7) pageNum = i + 1
                          else if (targetPage <= 4) pageNum = i + 1
                          else if (targetPage >= targetPages - 3) pageNum = targetPages - 6 + i
                          else pageNum = targetPage - 3 + i
                          return (
                            <button
                              key={pageNum}
                              type="button"
                              onClick={() => setTargetPage(pageNum)}
                              className={cn(
                                'flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs transition-colors',
                                targetPage === pageNum
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
            )}

            {activeTab === 'info' && (
              <div className="grid max-w-3xl gap-6">
                <section className="rounded-lg border border-border p-5">
                  <h2 className="mb-4 text-base font-semibold">基本信息</h2>
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <InfoItem label="任务名称" value={task.name} />
                    <InfoItem label="创建人" value={task.created_by_name || '-'} />
                    <InfoItem label="发送时间" value={task.send_type === 'immediate' ? '发布后立即发送' : formatDateTime(task.scheduled_at)} />
                    <InfoItem label="创建时间" value={formatDateTime(task.created_at)} />
                    <InfoItem label="发布时间" value={formatDateTime(task.published_at)} />
                    <InfoItem label="完成时间" value={formatDateTime(task.completed_at)} />
                    {task.description && (
                      <div className="col-span-2">
                        <dt className="mb-1 text-xs text-muted-foreground">任务说明</dt>
                        <dd>{task.description}</dd>
                      </div>
                    )}
                  </dl>
                </section>
                <section className="rounded-lg border border-border p-5">
                  <h2 className="mb-4 text-base font-semibold">短信内容</h2>
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <InfoItem label="短信模板" value={task.template_name} />
                    <InfoItem label="签名" value={task.sign_name} />
                  </dl>
                  <div className="mt-4">
                    <div className="mb-1.5 text-xs text-muted-foreground">正文快照</div>
                    <div className="rounded-md border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                      {renderSmsBody(task.body)}
                    </div>
                  </div>
                  {task.variables.length > 0 && (
                    <div className="mt-4 overflow-hidden rounded-md border border-border">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border bg-muted text-left text-xs text-muted-foreground">
                            <th className="px-3 py-2">变量</th>
                            <th className="px-3 py-2">说明</th>
                            <th className="px-3 py-2">是否必填</th>
                            <th className="px-3 py-2">最大长度</th>
                          </tr>
                        </thead>
                        <tbody>
                          {task.variables.map((v) => (
                            <tr key={v.key} className="border-b border-border last:border-0">
                              <td className="px-3 py-2 font-mono text-xs">{`{${v.key}}`}</td>
                              <td className="px-3 py-2">{v.label}</td>
                              <td className="px-3 py-2">{v.required ? '必填' : '选填'}</td>
                              <td className="px-3 py-2 text-muted-foreground">{v.max_length ?? '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              </div>
            )}
          </>
        )}
      </main>

      {templateForRender && (
        <>
          <SmsTaskImportDialog taskId={taskId} template={templateForRender} open={importOpen} onClose={() => setImportOpen(false)} />
          <SmsTaskTargetAddDialog taskId={taskId} template={templateForRender} open={addOpen} onClose={() => setAddOpen(false)} />
        </>
      )}
      {openTargetId !== null && (
        <SmsTaskTargetDetailDrawer taskId={taskId} targetId={openTargetId} onClose={() => setOpenTargetId(null)} />
      )}

      <ConfirmDialog
        open={confirmAction === 'publish'}
        title="发布任务"
        message={
          task.send_type === 'immediate'
            ? `发布后任务将立即开始发送（共 ${stats.total} 个对象），是否继续？`
            : `发布后任务将于 ${formatDateTime(task.scheduled_at)} 开始发送（共 ${stats.total} 个对象），是否继续？`
        }
        confirmLabel="确认发布"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'pause'}
        title="暂停任务"
        message="暂停后未发送的对象将停止发送，可随时恢复。"
        confirmLabel="确认暂停"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'resume'}
        title="恢复任务"
        message="恢复后将继续发送剩余待发送对象。"
        confirmLabel="确认恢复"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'archive'}
        title="归档任务"
        message="归档后任务变为只读，不再出现在默认列表中。"
        confirmLabel="确认归档"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'delete'}
        title="删除任务"
        message="删除后任务及其全部发送对象将被移除，此操作不可恢复。"
        itemName={task.name}
        confirmLabel="确定删除"
        variant="destructive"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'resend'}
        title="重发失败对象"
        message={`将把 ${stats.failed} 个失败对象重置为待发送并重新发送，是否继续？`}
        confirmLabel="确认重发"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'bulkDelete'}
        title="批量删除发送对象"
        message={`将删除选中的 ${selectedTargetIds.length} 个待发送对象，此操作不可恢复。`}
        confirmLabel="确定删除"
        variant="destructive"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
      <ConfirmDialog
        open={confirmAction === 'switchTemplate'}
        title="更换短信模板"
        message={`更换模板将清空当前任务下全部 ${stats.total} 个发送对象，是否继续？`}
        confirmLabel="确认更换"
        variant="destructive"
        onCancel={() => setConfirmAction(null)}
        onConfirm={handleConfirm}
      />
    </div>
  )
}

function toLocalInputValue(iso: string): string {
  const date = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function MetricCard({ label, value, tone }: { label: string; value: number | string; tone?: 'success' | 'info' | 'destructive' }) {
  const toneClass = tone === 'success' ? 'text-success' : tone === 'info' ? 'text-info' : tone === 'destructive' ? 'text-destructive' : 'text-foreground'
  return (
    <div className="rounded-lg border border-border px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-2xl font-semibold', toneClass)}>{value}</div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="mb-1 text-xs text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
