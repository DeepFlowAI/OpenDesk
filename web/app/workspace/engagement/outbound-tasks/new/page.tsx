'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { IconArrowLeft, IconPlayerPlay, IconSend } from '@tabler/icons-react'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import { OutboundScriptRunner } from '@/app/components/features/engagement/outbound-script-runner'
import { useAuthStore } from '@/context/auth-store'
import { useCreateOutboundTask, useOutboundTaskTemplate, useOutboundTaskTemplates } from '@/service/use-outbound-tasks'
import { FIELD_TYPE_LABELS } from '@/types/field-enums'

export default function NewOutboundTaskPage() {
  const router = useRouter()
  const user = useAuthStore((state) => state.user)
  const { data: templates, isLoading } = useOutboundTaskTemplates({ page: 1, per_page: 100 })
  const createTask = useCreateOutboundTask()
  const firstTemplateId = templates?.items[0]?.id ?? 0
  const [templateId, setTemplateId] = useState(0)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [allowSelfClaim, setAllowSelfClaim] = useState(false)
  const [scriptPreviewOpen, setScriptPreviewOpen] = useState(false)
  const selectedTemplate = useMemo(
    () => templates?.items.find((item) => item.id === (templateId || firstTemplateId)) ?? null,
    [firstTemplateId, templateId, templates?.items],
  )
  const { data: selectedTemplateDetail, isFetching: isScriptLoading } = useOutboundTaskTemplate(selectedTemplate?.id ?? 0)

  const handleSubmit = async (publish: boolean) => {
    if (!selectedTemplate) {
      toast.error('请选择任务模板')
      return
    }
    if (!name.trim()) {
      toast.error('请输入任务名称')
      return
    }
    try {
      const task = await createTask.mutateAsync({
        template_id: selectedTemplate.id,
        name: name.trim(),
        description: description.trim() || null,
        owner_id: user?.id ?? null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        allow_self_claim: allowSelfClaim,
        fields: selectedTemplate.fields,
        publish,
      })
      toast.success(publish ? '外呼任务已发布' : '草稿已保存')
      router.push(`/workspace/engagement/outbound-tasks/${task.id}`)
    } catch {
      toast.error('保存失败，请重试')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/workspace/engagement/outbound-tasks" className="rounded-md p-2 hover:bg-muted">
            <IconArrowLeft size={18} />
          </Link>
          <h1 className="text-xl font-semibold text-foreground">新建人工外呼任务</h1>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : (templates?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="暂无任务模板，请先创建模板"
            action={<Link href="/workspace/engagement/outbound-task-templates" className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">去创建模板</Link>}
          />
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">基础信息</h2>
              <div className="grid gap-4">
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务名称</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} className="h-10 rounded-md border border-border bg-background px-3 outline-none" />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务模板</span>
                  <select value={templateId || firstTemplateId} onChange={(e) => setTemplateId(Number(e.target.value))} className="h-10 rounded-md border border-border bg-background px-3">
                    {templates?.items.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
                  </select>
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务说明</span>
                  <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={4} className="rounded-md border border-border bg-background px-3 py-2 outline-none" />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">截止时间</span>
                  <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="h-10 rounded-md border border-border bg-background px-3 outline-none" />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={allowSelfClaim} onChange={(e) => setAllowSelfClaim(e.target.checked)} />
                  允许客服领取未分配对象
                </label>
              </div>
            </section>

            <section className="rounded-lg border border-border p-5">
              <div className="flex items-center justify-between gap-4">
                <div><h2 className="text-base font-semibold">外呼话术</h2><p className="mt-1 text-sm text-muted-foreground">{isScriptLoading ? '话术加载中...' : selectedTemplateDetail?.script ? `已配置 · ${selectedTemplateDetail.script.nodes.length} 个节点` : '所选模板未配置外呼话术'}</p></div>
                {selectedTemplateDetail?.script && <button type="button" onClick={() => setScriptPreviewOpen(true)} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"><IconPlayerPlay size={16} />预览话术</button>}
              </div>
            </section>

            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-3 text-base font-semibold">任务字段结构</h2>
              <div className="grid gap-2">
                {selectedTemplate?.fields.map((field) => (
                  <div key={field.key} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                    <span>{field.name}</span>
                    <span className="text-muted-foreground">{FIELD_TYPE_LABELS[field.field_type]?.zh ?? field.field_type}{field.agent_editable ? ' · 客服可编辑' : ''}</span>
                  </div>
                ))}
              </div>
            </section>

            <div className="flex justify-end gap-3">
              <button type="button" onClick={() => void handleSubmit(false)} className="rounded-md border border-border px-4 py-2 text-sm">保存草稿</button>
              <button type="button" onClick={() => void handleSubmit(true)} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
                <IconSend size={16} />
                发布任务
              </button>
            </div>
          </div>
        )}
      </main>
      {selectedTemplateDetail?.script && <OutboundScriptRunner open={scriptPreviewOpen} script={selectedTemplateDetail.script} title="预览话术流程" subtitle={selectedTemplateDetail.name} onClose={() => setScriptPreviewOpen(false)} />}
    </div>
  )
}
