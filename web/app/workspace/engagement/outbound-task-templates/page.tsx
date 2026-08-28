'use client'

import Link from 'next/link'
import { IconEdit, IconPlus, IconTrash } from '@tabler/icons-react'
import { toast } from 'sonner'
import { EmptyState, formatDateTime } from '@/app/components/features/engagement/outbound-task-ui'
import {
  useDeleteOutboundTaskTemplate,
  useOutboundTaskTemplates,
} from '@/service/use-outbound-tasks'

export default function OutboundTaskTemplatesPage() {
  const { data, isLoading } = useOutboundTaskTemplates({ page: 1, per_page: 50 })
  const deleteTemplate = useDeleteOutboundTaskTemplate()

  const handleDelete = async (id: number, templateName: string) => {
    if (!window.confirm(`确定删除任务模板「${templateName}」？`)) return
    try {
      await deleteTemplate.mutateAsync(id)
      toast.success('已删除')
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">任务模板</h1>
          <p className="mt-1 text-sm text-muted-foreground">配置创建外呼任务时复制的业务字段结构</p>
        </div>
        <Link
          href="/workspace/engagement/outbound-task-templates/new"
          className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground"
        >
          <IconPlus size={16} />
          新建模板
        </Link>
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">加载中...</div>
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="暂无任务模板"
            action={<Link href="/workspace/engagement/outbound-task-templates/new" className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">新建模板</Link>}
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">模板名称</th>
                  <th className="px-4 py-3 font-medium">说明</th>
                  <th className="px-4 py-3 font-medium">字段数</th>
                  <th className="px-4 py-3 font-medium">外呼话术</th>
                  <th className="px-4 py-3 font-medium">更新时间</th>
                  <th className="w-20 px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((template) => (
                  <tr key={template.id} className="border-t border-border">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/workspace/engagement/outbound-task-templates/${template.id}`} className="hover:underline">
                        {template.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{template.description || '-'}</td>
                    <td className="px-4 py-3">{template.fields.length}</td>
                    <td className="px-4 py-3">
                      <Link href={`/workspace/engagement/outbound-task-templates/${template.id}?tab=script`} className={template.has_script || template.script ? 'text-success hover:underline' : 'text-muted-foreground hover:underline'}>
                        {template.has_script || template.script ? '已配置' : '未配置'}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{formatDateTime(template.updated_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link title="编辑" href={`/workspace/engagement/outbound-task-templates/${template.id}`}>
                          <IconEdit size={17} />
                        </Link>
                        <button title="删除" onClick={() => void handleDelete(template.id, template.name)}>
                          <IconTrash size={17} />
                        </button>
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
