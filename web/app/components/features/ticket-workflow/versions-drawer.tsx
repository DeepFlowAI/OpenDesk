'use client'

import { IconArrowBackUp, IconEye, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import type { TicketWorkflowGraph } from '@/models/ticket-workflow-graph'
import {
  useRollbackTicketWorkflow,
  useTicketWorkflowVersions,
} from '@/service/use-ticket-workflows'

export function TicketWorkflowVersionsDrawer({
  workflowId,
  onClose,
  onPreview,
  onRollbackSuccess,
}: {
  workflowId: number
  onClose: () => void
  onPreview: (versionNo: number, graph: TicketWorkflowGraph) => void
  onRollbackSuccess: () => void
}) {
  const { data, isLoading } = useTicketWorkflowVersions(workflowId, true)
  const rollback = useRollbackTicketWorkflow(workflowId)

  const handlePreview = async (versionNo: number) => {
    const { get } = await import('@/service/base')
    try {
      const detail = await get<import('@/models/ticket-workflow').TicketWorkflowVersionDetail>(
        `v1/ticket-workflows/${workflowId}/versions/${versionNo}`,
      )
      onPreview(versionNo, detail.graph_json)
    } catch {
      toast.error('加载版本失败')
    }
  }

  const handleRollback = async (versionNo: number) => {
    if (!confirm(`回滚到版本 ${versionNo}？将创建一条新版本作为当前生效版本。`)) return
    try {
      await rollback.mutateAsync(versionNo)
      toast.success(`已回滚到版本 ${versionNo}`)
      onRollbackSuccess()
      onClose()
    } catch {
      toast.error('回滚失败')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 flex h-full w-[420px] flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="text-base font-semibold">历史版本</h3>
          <button type="button" onClick={onClose} className="text-foreground/60 hover:text-foreground">
            <IconX size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          {isLoading ? (
            <p className="px-3 text-sm text-muted-foreground">加载中...</p>
          ) : data?.items.length === 0 ? (
            <p className="px-3 text-sm text-muted-foreground">暂无历史版本</p>
          ) : (
            data?.items.map((version) => (
              <div key={version.id} className="mb-2 rounded-lg border border-border px-3 py-2 hover:bg-muted/40">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">v{version.version_no}</span>
                    {version.is_current && (
                      <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700">
                        当前
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handlePreview(version.version_no)}
                      className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-white"
                    >
                      <IconEye size={12} />
                      预览
                    </button>
                    {!version.is_current && (
                      <button
                        type="button"
                        onClick={() => handleRollback(version.version_no)}
                        className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-white"
                      >
                        <IconArrowBackUp size={12} />
                        回滚
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {version.created_at?.slice(0, 19).replace('T', ' ')}
                  {version.created_by_actor_name && ` · ${version.created_by_actor_name}`}
                </p>
                {version.comment && <p className="mt-1 text-xs text-foreground/70">{version.comment}</p>}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
