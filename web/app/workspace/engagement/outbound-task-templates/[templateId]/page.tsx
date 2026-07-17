'use client'

import { useParams } from 'next/navigation'
import { toast } from 'sonner'
import { OutboundTaskTemplateForm } from '@/app/components/features/engagement/outbound-task-template-form'
import { useOutboundTaskTemplate, useUpdateOutboundTaskTemplate } from '@/service/use-outbound-tasks'

export default function OutboundTaskTemplateDetailPage() {
  const params = useParams()
  const templateId = Number(params.templateId)
  const { data: template, isLoading } = useOutboundTaskTemplate(templateId)
  const updateTemplate = useUpdateOutboundTaskTemplate()

  return (
    <OutboundTaskTemplateForm
      title={template?.name ? `编辑模板：${template.name}` : '编辑任务模板'}
      submitLabel="保存模板"
      template={template}
      loading={isLoading}
      saving={updateTemplate.isPending}
      onSubmit={async (draft) => {
        if (!template) return
        if (!draft.name.trim()) {
          toast.error('请输入模板名称')
          return
        }
        if (draft.fields.some((field) => !field.name.trim())) {
          toast.error('请填写字段名称')
          return
        }
        try {
          await updateTemplate.mutateAsync({
            id: template.id,
            data: {
              name: draft.name.trim(),
              description: draft.description.trim() || null,
              fields: draft.fields.map((field) => ({ ...field, name: field.name.trim() })),
            },
          })
          toast.success('任务模板已保存')
        } catch {
          toast.error('保存失败，请重试')
        }
      }}
    />
  )
}
