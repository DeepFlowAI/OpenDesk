'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { IconArrowLeft, IconSend } from '@tabler/icons-react'
import { EmptyState, renderSmsBody } from '@/app/components/features/engagement/sms-bulk-task-ui'
import { useCreateSmsBulkTask, useSmsBulkAvailableTemplates } from '@/service/use-sms-bulk-tasks'
import type { SmsBulkSendType } from '@/models/sms-bulk-task'

export default function NewSmsBulkTaskPage() {
  const router = useRouter()
  const { data: templates, isLoading } = useSmsBulkAvailableTemplates()
  const createTask = useCreateSmsBulkTask()
  const [templateId, setTemplateId] = useState(0)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [sendType, setSendType] = useState<SmsBulkSendType>('immediate')
  const [scheduledAt, setScheduledAt] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const items = useMemo(() => templates?.items ?? [], [templates?.items])
  const selectedTemplate = useMemo(
    () => items.find((item) => item.id === templateId) ?? null,
    [items, templateId],
  )

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error('请输入任务名称')
      return
    }
    if (!selectedTemplate) {
      toast.error('请选择短信模板')
      return
    }
    if (sendType === 'scheduled') {
      if (!scheduledAt) {
        toast.error('请选择定时发送时间')
        return
      }
      if (new Date(scheduledAt).getTime() <= Date.now()) {
        toast.error('定时发送时间需晚于当前时间')
        return
      }
    }
    setSubmitting(true)
    try {
      const task = await createTask.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        template_id: selectedTemplate.id,
        send_type: sendType,
        scheduled_at: sendType === 'scheduled' ? new Date(scheduledAt).toISOString() : null,
      })
      toast.success('任务已创建，请添加发送对象')
      router.push(`/workspace/engagement/sms-tasks/${task.id}`)
    } catch {
      toast.error('创建失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-4">
        <Link href="/workspace/engagement/sms-tasks" className="rounded-md p-2 hover:bg-muted">
          <IconArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">新建短信群发任务</h1>
          <p className="mt-1 text-sm text-muted-foreground">选择模板并配置发送时间，创建后添加发送对象</p>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : items.length === 0 ? (
          <EmptyState title="暂无可用短信模板，请联系管理员在短信设置中配置模板与授权" />
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">基本信息</h2>
              <div className="grid gap-4">
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务名称 <span className="text-destructive">*</span></span>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：618 大促活动通知"
                    className="h-10 rounded-md border border-border bg-background px-3 outline-none"
                  />
                </label>
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">任务说明</span>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="选填，记录本次群发的目的与范围"
                    className="rounded-md border border-border bg-background px-3 py-2 outline-none"
                  />
                </label>
              </div>
            </section>

            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">短信内容</h2>
              <div className="grid gap-4">
                <label className="grid gap-1.5 text-sm">
                  <span className="font-medium">短信模板 <span className="text-destructive">*</span></span>
                  <select
                    value={templateId}
                    onChange={(e) => setTemplateId(Number(e.target.value))}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  >
                    <option value={0} disabled>请选择模板</option>
                    {items.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name}（{template.sign_name}）
                      </option>
                    ))}
                  </select>
                </label>

                {selectedTemplate && (
                  <>
                    <div>
                      <div className="mb-1.5 text-sm font-medium">正文预览</div>
                      <div className="rounded-md border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                        {renderSmsBody(selectedTemplate.body)}
                      </div>
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        高亮部分为变量，发送时将替换为每个对象的变量值
                      </p>
                    </div>
                    {selectedTemplate.variables.length > 0 && (
                      <div>
                        <div className="mb-1.5 text-sm font-medium">变量说明</div>
                        <div className="overflow-hidden rounded-md border border-border">
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
                              {selectedTemplate.variables.map((v) => (
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
                      </div>
                    )}
                  </>
                )}
              </div>
            </section>

            <section className="rounded-lg border border-border p-5">
              <h2 className="mb-4 text-base font-semibold">发送时间</h2>
              <div className="grid gap-3 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="send-type"
                    checked={sendType === 'immediate'}
                    onChange={() => setSendType('immediate')}
                  />
                  发布后立即发送
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="send-type"
                    checked={sendType === 'scheduled'}
                    onChange={() => setSendType('scheduled')}
                  />
                  定时发送
                </label>
                {sendType === 'scheduled' && (
                  <input
                    type="datetime-local"
                    value={scheduledAt}
                    onChange={(e) => setScheduledAt(e.target.value)}
                    className="h-10 w-64 rounded-md border border-border bg-background px-3 outline-none"
                  />
                )}
              </div>
            </section>

            <div className="flex justify-end gap-3">
              <Link
                href="/workspace/engagement/sms-tasks"
                className="rounded-md border border-border px-4 py-2 text-sm"
              >
                取消
              </Link>
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleSubmit()}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                <IconSend size={16} />
                保存并继续
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
