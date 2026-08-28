'use client'

import { useState } from 'react'
import { IconHistory, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type { SatisfactionFlowVersionDetail } from '@/models/satisfaction-flow'
import {
  useRollbackSatisfactionFlow,
  useSatisfactionFlowVersions,
} from '@/service/use-satisfaction-flows'
import { get } from '@/service/base'

export function SatisfactionVersionsDrawer({ flowId, open, onClose, onPreview, onRestored }: {
  flowId: number
  open: boolean
  onClose: () => void
  onPreview: (version: SatisfactionFlowVersionDetail) => void
  onRestored: () => void
}) {
  const [restoreNo, setRestoreNo] = useState<number | null>(null)
  const versions = useSatisfactionFlowVersions(flowId, open)
  const rollback = useRollbackSatisfactionFlow(flowId)
  if (!open) return null
  return (
    <>
      <aside className="absolute inset-y-0 right-0 z-30 w-[390px] border-l border-border bg-card shadow-2xl">
        <header className="flex h-14 items-center justify-between border-b border-border px-5"><div className="flex items-center gap-2"><IconHistory size={17} /><h2 className="text-sm font-semibold">历史版本</h2></div><button type="button" onClick={onClose} aria-label="关闭历史版本"><IconX size={18} /></button></header>
        <div className="space-y-3 overflow-y-auto p-5">
          {versions.isLoading && <p className="text-sm text-muted-foreground">加载中...</p>}
          {versions.data?.items.map((item) => (
            <div key={item.id} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between"><p className="font-mono text-sm font-semibold">V{item.version_no}</p>{item.is_current && <span className="rounded-md bg-success/10 px-2 py-1 text-xs text-success">当前</span>}</div>
              <p className="mt-2 text-sm">{item.name_snapshot}</p><p className="mt-1 text-xs text-muted-foreground">{item.question_count} 个问题 · {item.created_by_actor_name || '—'}</p>
              <div className="mt-3 flex gap-2"><button type="button" onClick={async () => { const version = await get<SatisfactionFlowVersionDetail>(`v1/satisfaction-flows/${flowId}/versions/${item.version_no}`); onPreview(version) }} className="rounded-md border border-border px-2 py-1 text-xs">查看</button>{!item.is_current && <button type="button" onClick={() => setRestoreNo(item.version_no)} className="rounded-md border border-border px-2 py-1 text-xs">恢复为新版本</button>}</div>
            </div>
          ))}
        </div>
      </aside>
      <ConfirmDialog open={restoreNo !== null} title="恢复满意度流程版本" message="历史版本将复制为新的当前版本，不会覆盖已有版本。" itemName={restoreNo === null ? undefined : `V${restoreNo}`} loading={rollback.isPending} onCancel={() => setRestoreNo(null)} onConfirm={async () => { if (restoreNo === null) return; try { await rollback.mutateAsync(restoreNo); toast.success('已恢复为新版本'); setRestoreNo(null); onRestored() } catch { toast.error('版本恢复失败') } }} />
    </>
  )
}
