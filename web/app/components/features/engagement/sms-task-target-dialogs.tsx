'use client'

import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { IconLoader2, IconX } from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  formatDateTime,
  renderSmsBody,
  SmsTargetStatusBadge,
} from '@/app/components/features/engagement/sms-bulk-task-ui'
import { useCreateSmsBulkTarget, useSmsBulkTargetDetail } from '@/service/use-sms-bulk-tasks'
import type { SmsBulkTemplateItem } from '@/models/sms-bulk-task'

const CN_MOBILE_PATTERN = /^1[3-9]\d{9}$/

export function SmsTaskTargetAddDialog({
  taskId,
  template,
  open,
  onClose,
}: {
  taskId: number
  template: SmsBulkTemplateItem
  open: boolean
  onClose: () => void
}) {
  const createTarget = useCreateSmsBulkTarget(taskId)
  const [phone, setPhone] = useState('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  const previewValues = useMemo(() => {
    const result: Record<string, string> = {}
    template.variables.forEach((v) => {
      if (values[v.key]) result[v.key] = values[v.key]
    })
    return result
  }, [template.variables, values])

  const reset = () => {
    setPhone('')
    setValues({})
    setSubmitting(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async () => {
    const trimmedPhone = phone.trim()
    if (!CN_MOBILE_PATTERN.test(trimmedPhone)) {
      toast.error('请输入正确的手机号码')
      return
    }
    const missing = template.variables.filter((v) => v.required && !values[v.key]?.trim())
    if (missing.length > 0) {
      toast.error(`请填写必填变量：${missing.map((v) => v.label).join('、')}`)
      return
    }
    setSubmitting(true)
    try {
      await createTarget.mutateAsync({ phone: trimmedPhone, variable_values: values })
      toast.success('发送对象已添加')
      handleClose()
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status
      toast.error(status === 409 ? '该号码已存在于当前任务' : '添加失败，请重试')
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>添加发送对象</DialogTitle>
          <DialogDescription>单个添加接收号码并填写模板变量值</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">接收号码 <span className="text-destructive">*</span></span>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="请输入 11 位手机号"
              className="h-10 rounded-md border border-border bg-background px-3 outline-none"
            />
          </label>
          {template.variables.map((v) => (
            <label key={v.key} className="grid gap-1.5 text-sm">
              <span className="font-medium">
                {v.label} <span className="font-mono text-xs text-muted-foreground">{`{${v.key}}`}</span>
                {v.required && <span className="text-destructive"> *</span>}
              </span>
              <input
                value={values[v.key] ?? ''}
                onChange={(e) => setValues((prev) => ({ ...prev, [v.key]: e.target.value }))}
                maxLength={v.max_length ?? undefined}
                className="h-10 rounded-md border border-border bg-background px-3 outline-none"
              />
            </label>
          ))}
          <div>
            <div className="mb-1.5 text-sm font-medium">正文预览</div>
            <div className="rounded-md border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
              {renderSmsBody(template.body, previewValues)}
            </div>
          </div>
        </div>
        <DialogFooter>
          <button type="button" onClick={handleClose} className="rounded-md border border-border px-4 py-2 text-sm">
            取消
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void handleSubmit()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {submitting ? '提交中...' : '确定添加'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function SmsTaskTargetDetailDrawer({
  taskId,
  targetId,
  onClose,
}: {
  taskId: number
  targetId: number
  onClose: () => void
}) {
  const { data, isLoading } = useSmsBulkTargetDetail(taskId, targetId)

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-[440px] flex-col border-l border-border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">发送对象详情</h2>
          <button type="button" onClick={onClose} aria-label="关闭" className="text-muted-foreground hover:text-foreground">
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
              <div>
                <div className="mb-1 text-xs text-muted-foreground">接收号码</div>
                <div className="font-mono font-medium">{data.phone}</div>
              </div>
              <div>
                <div className="mb-1 text-xs text-muted-foreground">状态</div>
                <SmsTargetStatusBadge status={data.status} />
              </div>
              {data.fail_reason && (
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">失败原因</div>
                  <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                    {data.fail_reason}
                  </div>
                </div>
              )}
              {Object.keys(data.variable_values).length > 0 && (
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">变量值</div>
                  <div className="overflow-hidden rounded-md border border-border">
                    {Object.entries(data.variable_values).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-3 border-b border-border px-3 py-2 last:border-0">
                        <span className="font-mono text-xs text-muted-foreground">{`{${key}}`}</span>
                        <span className="text-right">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <div className="mb-1 text-xs text-muted-foreground">短信正文</div>
                <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 leading-6">
                  {data.body_rendered}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">提交时间</div>
                  <div>{formatDateTime(data.submitted_at)}</div>
                </div>
                <div>
                  <div className="mb-1 text-xs text-muted-foreground">送达时间</div>
                  <div>{formatDateTime(data.delivered_at)}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
