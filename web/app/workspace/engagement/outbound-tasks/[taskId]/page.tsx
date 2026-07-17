'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useMemo, useState } from 'react'
import { IconArrowLeft, IconPlus, IconTrash, IconUpload, IconUserCheck } from '@tabler/icons-react'
import { toast } from 'sonner'
import {
  EmptyState,
  formatDateTime,
  formatPercent,
  TargetStatusBadge,
  TaskStatusBadge,
} from '@/app/components/features/engagement/outbound-task-ui'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useEmployees } from '@/service/use-employees'
import {
  useBulkAssignOutboundTargets,
  useBulkDeleteOutboundTargets,
  useCreateOutboundTarget,
  useImportOutboundTargets,
  useOutboundRecords,
  useOutboundTargets,
  useOutboundTask,
  useTransitionOutboundTask,
} from '@/service/use-outbound-tasks'
import type { OutboundTargetImportResponse, OutboundTaskField } from '@/models/outbound-task'

type DetailTab = 'targets' | 'records'
type TargetActionModal = 'add' | 'import' | 'assign' | 'delete' | null

export default function OutboundTaskDetailPage() {
  const params = useParams()
  const taskId = Number(params.taskId)
  const [selectedTargetIds, setSelectedTargetIds] = useState<number[]>([])
  const [activeTab, setActiveTab] = useState<DetailTab>('targets')
  const [targetModal, setTargetModal] = useState<TargetActionModal>(null)
  const [targetNumbers, setTargetNumbers] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [assignAssigneeId, setAssignAssigneeId] = useState<number | ''>('')
  const { data: task, isLoading } = useOutboundTask(taskId)
  const { data: targets } = useOutboundTargets(taskId, { page: 1, per_page: 100 })
  const { data: records } = useOutboundRecords(taskId, { page: 1, per_page: 50 })
  const { data: employees } = useEmployees({ page: 1, per_page: 100, status: 'active' })
  const createTarget = useCreateOutboundTarget(taskId)
  const importTargets = useImportOutboundTargets(taskId)
  const bulkAssign = useBulkAssignOutboundTargets(taskId)
  const bulkDelete = useBulkDeleteOutboundTargets(taskId)
  const transition = useTransitionOutboundTask()

  const employeeNameById = useMemo(() => {
    const map = new Map<number, string>()
    employees?.items.forEach((employee) => map.set(employee.id, employee.name))
    return map
  }, [employees?.items])

  const toggleTarget = (id: number) => {
    setSelectedTargetIds((ids) => ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id])
  }

  const handleCreateTargets = async () => {
    const phoneNumbers = parsePhoneNumbers(targetNumbers)
    if (phoneNumbers.length === 0) {
      toast.error('请输入至少一个呼叫号码')
      return
    }
    let created = 0
    try {
      for (const phoneNumber of phoneNumbers) {
        await createTarget.mutateAsync({
          phone_number: phoneNumber,
          field_values: {},
        })
        created += 1
      }
    } catch {
      toast.error(created > 0 ? `已添加 ${created} 个，剩余号码添加失败` : '添加失败，请重试')
      return
    }
    setTargetNumbers('')
    setTargetModal(null)
    setActiveTab('targets')
    toast.success(`已添加 ${created} 个外呼对象`)
  }

  const handleImportTargets = async () => {
    if (!importFile) {
      toast.error('请选择导入文件')
      return
    }
    try {
      const result = await importTargets.mutateAsync(importFile)
      setActiveTab('targets')
      if (result.failed > 0) {
        toast.error(`导入完成，成功 ${result.created} 行，失败 ${result.failed} 行`)
        return
      }
      setImportFile(null)
      setTargetModal(null)
      toast.success(`已导入 ${result.created} 个外呼对象`)
    } catch {
      toast.error('导入失败，请检查文件格式')
    }
  }

  const openImportModal = () => {
    setImportFile(null)
    importTargets.reset()
    setTargetModal('import')
  }

  const openAssignModal = () => {
    if (selectedTargetIds.length === 0) {
      toast.error('请选择外呼对象')
      return
    }
    setAssignAssigneeId('')
    setTargetModal('assign')
  }

  const handleAssign = async () => {
    if (assignAssigneeId === '') {
      toast.error('请选择客服')
      return
    }
    try {
      const res = await bulkAssign.mutateAsync({
        target_ids: selectedTargetIds,
        assignee_id: assignAssigneeId,
        overwrite: true,
      })
      setSelectedTargetIds([])
      setAssignAssigneeId('')
      setTargetModal(null)
      toast.success(`已分配 ${res.updated} 个外呼对象`)
    } catch {
      toast.error('分配失败，请重试')
    }
  }

  const handleDeleteTargets = async () => {
    try {
      const result = await bulkDelete.mutateAsync({ target_ids: selectedTargetIds })
      setSelectedTargetIds([])
      setTargetModal(null)
      toast.success(`已删除 ${result.deleted} 个外呼对象`)
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  const runTransition = async (action: 'publish' | 'pause' | 'resume' | 'archive') => {
    try {
      await transition.mutateAsync({ id: taskId, action })
      toast.success('操作成功')
    } catch {
      toast.error('操作失败，请检查任务配置')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/workspace/engagement/outbound-tasks" className="rounded-md p-2 hover:bg-muted">
            <IconArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-foreground">{task?.name ?? '外呼任务'}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{task?.template_name ?? '-'}</p>
          </div>
          {task && <TaskStatusBadge status={task.status} />}
        </div>
        {task && (
          <div className="flex gap-2">
            {task.status === 'draft' && <button onClick={() => void runTransition('publish')} className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">发布</button>}
            {task.status === 'active' && <button onClick={() => void runTransition('pause')} className="rounded-md border border-border px-3 py-2 text-sm">暂停</button>}
            {task.status === 'paused' && <button onClick={() => void runTransition('resume')} className="rounded-md border border-border px-3 py-2 text-sm">恢复</button>}
            {(task.status === 'paused' || task.status === 'completed') && <button onClick={() => void runTransition('archive')} className="rounded-md border border-border px-3 py-2 text-sm">归档</button>}
          </div>
        )}
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading || !task ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : (
          <div className="space-y-6">
            <section className="grid gap-4 md:grid-cols-5">
              <Metric label="外呼对象总数" value={task.stats.total_targets} />
              <Metric label="待呼叫" value={task.stats.pending_targets} />
              <Metric label="已完成" value={task.stats.completed_targets} />
              <Metric label="呼叫次数" value={task.stats.call_count} />
              <Metric label="接通率" value={formatPercent(task.stats.answered_count, task.stats.call_count)} />
            </section>

            <section className="rounded-lg border border-border p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-base font-semibold">添加与分配对象</h2>
                  <p className="mt-1 text-sm text-muted-foreground">通过添加、导入或勾选后分配来维护外呼对象名单。</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => setTargetModal('add')} className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm">
                    <IconPlus size={16} />
                    添加
                  </button>
                  <button onClick={openImportModal} className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm">
                    <IconUpload size={16} />
                    导入
                  </button>
                  <button onClick={openAssignModal} className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm text-primary-foreground">
                    <IconUserCheck size={16} />
                    分配
                  </button>
                </div>
              </div>
            </section>

            <section>
              <div className="flex items-center justify-between border-b border-border px-4 pt-4">
                <div role="tablist" aria-label="外呼任务详情" className="flex gap-6">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'targets'}
                    onClick={() => setActiveTab('targets')}
                    className={`border-b-2 px-1 pb-3 text-sm font-medium transition-colors ${
                      activeTab === 'targets'
                        ? 'border-foreground text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    外呼对象
                    <span className="ml-2 text-xs text-muted-foreground">{targets?.total ?? 0}</span>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'records'}
                    onClick={() => setActiveTab('records')}
                    className={`border-b-2 px-1 pb-3 text-sm font-medium transition-colors ${
                      activeTab === 'records'
                        ? 'border-foreground text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    外呼记录
                    <span className="ml-2 text-xs text-muted-foreground">{records?.total ?? 0}</span>
                  </button>
                </div>
                {activeTab === 'targets' && (
                  <button
                    type="button"
                    onClick={() => setTargetModal('delete')}
                    disabled={selectedTargetIds.length === 0 || task.status === 'archived' || bulkDelete.isPending}
                    className="mb-3 inline-flex h-9 items-center justify-center gap-2 rounded-md border border-destructive/40 px-3 text-sm text-destructive transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50"
                  >
                    <IconTrash size={16} />
                    删除
                  </button>
                )}
              </div>

              <div className="p-4">
                {activeTab === 'targets' ? (
                  (targets?.items.length ?? 0) === 0 ? (
                    <EmptyState title="暂无外呼对象" />
                  ) : (
                    <div className="overflow-hidden rounded-lg border border-border">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-left text-muted-foreground">
                          <tr>
                            <th className="w-10 px-4 py-3"></th>
                            <th className="px-4 py-3 font-medium">呼叫号码</th>
                            <th className="px-4 py-3 font-medium">分配客服</th>
                            <th className="px-4 py-3 font-medium">状态</th>
                            <th className="px-4 py-3 font-medium">呼叫次数</th>
                            <th className="px-4 py-3 font-medium">最近结果</th>
                            <th className="px-4 py-3 font-medium">下次跟进</th>
                          </tr>
                        </thead>
                        <tbody>
                          {targets?.items.map((target) => (
                            <tr key={target.id} className="border-t border-border">
                              <td className="px-4 py-3">
                                <input type="checkbox" checked={selectedTargetIds.includes(target.id)} onChange={() => toggleTarget(target.id)} />
                              </td>
                              <td className="px-4 py-3 font-medium">{target.phone_number}</td>
                              <td className="px-4 py-3">{target.assignee_id ? employeeNameById.get(target.assignee_id) ?? `#${target.assignee_id}` : '未分配'}</td>
                              <td className="px-4 py-3"><TargetStatusBadge status={target.status} /></td>
                              <td className="px-4 py-3">{target.call_count}</td>
                              <td className="px-4 py-3">{target.last_call_result || '-'}</td>
                              <td className="px-4 py-3">{formatDateTime(target.next_follow_up_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                ) : (
                  (records?.items.length ?? 0) === 0 ? (
                    <EmptyState title="暂无外呼记录" />
                  ) : (
                    <div className="overflow-hidden rounded-lg border border-border">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/60 text-left text-muted-foreground">
                          <tr>
                            <th className="px-4 py-3 font-medium">号码</th>
                            <th className="px-4 py-3 font-medium">客服</th>
                            <th className="px-4 py-3 font-medium">开始时间</th>
                            <th className="px-4 py-3 font-medium">接通</th>
                            <th className="px-4 py-3 font-medium">结果</th>
                            <th className="px-4 py-3 font-medium">备注</th>
                          </tr>
                        </thead>
                        <tbody>
                          {records?.items.map((record) => (
                            <tr key={record.id} className="border-t border-border">
                              <td className="px-4 py-3">{record.phone_number}</td>
                              <td className="px-4 py-3">{record.agent_id ? employeeNameById.get(record.agent_id) ?? `#${record.agent_id}` : '-'}</td>
                              <td className="px-4 py-3">{formatDateTime(record.started_at)}</td>
                              <td className="px-4 py-3">{record.answered ? '已接通' : '未接通'}</td>
                              <td className="px-4 py-3">{record.result || '-'}</td>
                              <td className="px-4 py-3">{record.notes || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}
              </div>
            </section>
          </div>
        )}
      </main>

      <AddTargetsDialog
        open={targetModal === 'add'}
        value={targetNumbers}
        submitting={createTarget.isPending}
        onChange={setTargetNumbers}
        onClose={() => setTargetModal(null)}
        onSubmit={() => void handleCreateTargets()}
      />
      <ImportTargetsDialog
        open={targetModal === 'import'}
        fields={task?.fields ?? []}
        file={importFile}
        result={importTargets.data}
        submitting={importTargets.isPending}
        onFileChange={setImportFile}
        onClose={() => setTargetModal(null)}
        onSubmit={() => void handleImportTargets()}
      />
      <AssignTargetsDialog
        open={targetModal === 'assign'}
        selectedCount={selectedTargetIds.length}
        employees={employees?.items ?? []}
        assigneeId={assignAssigneeId}
        submitting={bulkAssign.isPending}
        onAssigneeChange={setAssignAssigneeId}
        onClose={() => setTargetModal(null)}
        onSubmit={() => void handleAssign()}
      />
      <DeleteTargetsDialog
        open={targetModal === 'delete'}
        selectedCount={selectedTargetIds.length}
        submitting={bulkDelete.isPending}
        onClose={() => setTargetModal(null)}
        onSubmit={() => void handleDeleteTargets()}
      />
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function DeleteTargetsDialog({
  open,
  selectedCount,
  submitting,
  onClose,
  onSubmit,
}: {
  open: boolean
  selectedCount: number
  submitting: boolean
  onClose: () => void
  onSubmit: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>删除外呼对象</DialogTitle>
          <DialogDescription>确定删除选中的外呼对象？删除后不可恢复，相关外呼记录也将一并删除。</DialogDescription>
        </DialogHeader>
        <div className="rounded-md border border-border p-3 text-sm font-medium">
          已选择 {selectedCount} 个外呼对象
        </div>
        <DialogFooter className="pb-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md border border-border px-3 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || selectedCount === 0}
            className="inline-flex h-10 items-center justify-center rounded-md bg-destructive px-3 text-sm text-white disabled:opacity-50"
          >
            {submitting ? '删除中...' : '确定删除'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddTargetsDialog({
  open,
  value,
  submitting,
  onChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  value: string
  submitting: boolean
  onChange: (value: string) => void
  onClose: () => void
  onSubmit: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>添加外呼对象</DialogTitle>
          <DialogDescription>输入呼叫号码，支持中文逗号、英文逗号或换行分隔。</DialogDescription>
        </DialogHeader>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={'13800000000, 13900000000\n13700000000'}
          className="min-h-40 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-foreground/40"
        />
        <DialogFooter className="pb-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md border border-border px-3 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
          >
            {submitting ? '添加中...' : '添加'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ImportTargetsDialog({
  open,
  fields,
  file,
  result,
  submitting,
  onFileChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  fields: OutboundTaskField[]
  file: File | null
  result: OutboundTargetImportResponse | undefined
  submitting: boolean
  onFileChange: (file: File | null) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const enabledFields = fields.filter((field) => field.enabled)

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>导入外呼对象</DialogTitle>
          <DialogDescription>上传 Excel 文件，表头需包含「呼叫号码」，模板字段可使用字段名称或字段 key。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <label className="block rounded-lg border border-dashed border-border p-4">
            <span className="block text-sm font-medium">选择文件</span>
            <span className="mt-1 block text-xs text-muted-foreground">支持 .xlsx / .csv，首行作为表头。</span>
            <input
              type="file"
              accept=".xlsx,.csv"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
              className="mt-3 block w-full text-sm"
            />
            {file && <span className="mt-2 block text-xs text-muted-foreground">{file.name}</span>}
          </label>
          <div className="rounded-lg bg-muted/40 p-3 text-sm">
            <p className="font-medium">可导入字段</p>
            <p className="mt-1 text-xs text-muted-foreground">必填列：呼叫号码。模板字段：{enabledFields.length ? enabledFields.map((field) => field.name).join('、') : '无'}</p>
          </div>
          {result && result.failed > 0 && (
            <div className="max-h-40 overflow-auto rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
              <p className="font-medium text-destructive">失败 {result.failed} 行</p>
              <ul className="mt-2 space-y-1 text-xs text-destructive">
                {result.errors.slice(0, 10).map((error) => (
                  <li key={`${error.row_number}-${error.reason}`}>第 {error.row_number} 行：{error.reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <DialogFooter className="pb-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md border border-border px-3 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
          >
            {submitting ? '导入中...' : '导入'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AssignTargetsDialog({
  open,
  selectedCount,
  employees,
  assigneeId,
  submitting,
  onAssigneeChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  selectedCount: number
  employees: Array<{ id: number; name: string }>
  assigneeId: number | ''
  submitting: boolean
  onAssigneeChange: (value: number | '') => void
  onClose: () => void
  onSubmit: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>分配外呼对象</DialogTitle>
          <DialogDescription>已选择 {selectedCount} 个外呼对象，选择客服后将批量分配。</DialogDescription>
        </DialogHeader>
        <select
          value={assigneeId}
          onChange={(event) => onAssigneeChange(event.target.value ? Number(event.target.value) : '')}
          className="h-10 rounded-md border border-border bg-background px-3 text-sm outline-none"
        >
          <option value="">选择客服</option>
          {employees.map((employee) => (
            <option key={employee.id} value={employee.id}>{employee.name}</option>
          ))}
        </select>
        <DialogFooter className="pb-0">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md border border-border px-3 text-sm disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
          >
            {submitting ? '分配中...' : '分配'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function parsePhoneNumbers(value: string): string[] {
  const seen = new Set<string>()
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
}
