'use client'

import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { OutboundTaskTemplateForm } from '@/app/components/features/engagement/outbound-task-template-form'
import { useCreateOutboundTaskTemplate } from '@/service/use-outbound-tasks'

export default function NewOutboundTaskTemplatePage() {
  const router = useRouter()
  const createTemplate = useCreateOutboundTaskTemplate()

  return (
    <OutboundTaskTemplateForm
      title="新建任务模板"
      submitLabel="保存模板"
      saving={createTemplate.isPending}
      onSubmit={async (draft) => {
        if (!draft.name.trim()) {
          toast.error('请输入模板名称')
          return
        }
        if (draft.fields.some((field) => !field.name.trim())) {
          toast.error('请填写字段名称')
          return
        }
        try {
          const template = await createTemplate.mutateAsync({
            name: draft.name.trim(),
            description: draft.description.trim() || null,
            fields: draft.fields.map((field) => ({ ...field, name: field.name.trim() })),
          })
          toast.success('任务模板已保存')
          router.push(`/workspace/engagement/outbound-task-templates/${template.id}`)
        } catch {
          toast.error('保存失败，请重试')
        }
      }}
    />
  )
}
