'use client'
import { IconX, IconArrowBackUp, IconEye } from '@tabler/icons-react'
import { toast } from 'sonner'
import {
  useRollbackVoiceFlow,
  useVoiceFlowVersion,
  useVoiceFlowVersions,
} from '@/service/use-voice-flows'
import type { VoiceFlowGraph } from '@/models/voice-flow-graph'

type Props = {
  flowId: number
  onClose: () => void
  onPreview: (version_no: number, graph: VoiceFlowGraph) => void
  onRollbackSuccess: () => void
}

export function VersionsDrawer({ flowId, onClose, onPreview, onRollbackSuccess }: Props) {
  const { data, isLoading } = useVoiceFlowVersions(flowId, true)
  const rollback = useRollbackVoiceFlow(flowId)
  const previewVer = usePreview(flowId)

  const handlePreview = async (version_no: number) => {
    const detail = await previewVer.fetch(version_no)
    if (detail) onPreview(version_no, detail.graph_json)
  }

  const handleRollback = async (version_no: number) => {
    if (!confirm(`回滚到版本 ${version_no}？将创建一条新版本作为当前生效版本。`)) return
    try {
      await rollback.mutateAsync(version_no)
      toast.success(`已回滚到版本 ${version_no}`)
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
            data?.items.map((v) => (
              <div
                key={v.id}
                className="mb-2 rounded-lg border border-border px-3 py-2 hover:bg-muted/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">v{v.version_no}</span>
                    {v.is_current && (
                      <span className="rounded bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700">
                        当前
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handlePreview(v.version_no)}
                      className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-white"
                    >
                      <IconEye size={12} /> 预览
                    </button>
                    {!v.is_current && (
                      <button
                        type="button"
                        onClick={() => handleRollback(v.version_no)}
                        className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs hover:bg-white"
                      >
                        <IconArrowBackUp size={12} /> 回滚
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {v.created_at?.slice(0, 19).replace('T', ' ')}
                  {v.created_by_actor_name && ` · ${v.created_by_actor_name}`}
                </p>
                {v.comment && <p className="mt-1 text-xs text-foreground/70">{v.comment}</p>}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

// Lazy-load preview helper — we don't know the versionNo at render time.
function usePreview(flowId: number) {
  // Hook caches by [flowId, versionNo]. We trigger by setting versionNo via a setter
  // but here we just provide an ad-hoc fetch via the existing get helper.
  const fetch = async (versionNo: number) => {
    const { get } = await import('@/service/base')
    try {
      return await get<import('@/service/use-voice-flows').VoiceFlowVersionDetail>(
        `v1/voice-flows/${flowId}/versions/${versionNo}`,
      )
    } catch {
      toast.error('加载版本失败')
      return null
    }
  }
  return { fetch }
}

// Re-export the per-version detail hook so callers can use it ergonomically.
export { useVoiceFlowVersion }
