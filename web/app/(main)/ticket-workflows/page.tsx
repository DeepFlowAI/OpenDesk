'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconGripVertical, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react'
import { Switch } from '@/components/ui/switch'
import {
  useDeleteTicketWorkflow,
  useReorderTicketWorkflows,
  useTicketWorkflows,
  useUpdateTicketWorkflow,
} from '@/service/use-ticket-workflows'
import type { TicketWorkflowListItem } from '@/models/ticket-workflow'

function eventSummary(events: string[]): string {
  if (events.includes('create') && events.includes('update')) return '新建与编辑'
  if (events.includes('create')) return '仅新建'
  if (events.includes('update')) return '仅编辑'
  return '—'
}

export default function TicketWorkflowsPage() {
  const router = useRouter()
  const { data, isLoading, refetch } = useTicketWorkflows({ page: 1, per_page: 100 })
  const deleteMutation = useDeleteTicketWorkflow()
  const updateMutation = useUpdateTicketWorkflow()
  const reorderMutation = useReorderTicketWorkflows()

  const items = useMemo(() => data?.items ?? [], [data?.items])
  const [orderedIds, setOrderedIds] = useState<number[]>([])
  const [sorting, setSorting] = useState(false)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TicketWorkflowListItem | null>(null)

  useEffect(() => {
    if (!sorting) setOrderedIds(items.map((item) => item.id))
  }, [items, sorting])

  const byId = useMemo(() => Object.fromEntries(items.map((item) => [item.id, item])), [items])
  const rows = orderedIds.map((id) => byId[id]).filter(Boolean) as TicketWorkflowListItem[]

  const handleDrop = (toIndex: number) => {
    if (dragIndex == null || dragIndex === toIndex) {
      setDragIndex(null)
      return
    }
    const next = [...orderedIds]
    const [removed] = next.splice(dragIndex, 1)
    next.splice(toIndex, 0, removed)
    setOrderedIds(next)
    setDragIndex(null)
  }

  const saveOrder = async () => {
    await reorderMutation.mutateAsync(orderedIds)
    setSorting(false)
    refetch()
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[#1a1a1a]">流程引擎</h1>
        <div className="flex items-center gap-2">
          {sorting ? (
            <>
              <button type="button" onClick={() => { setSorting(false); setOrderedIds(items.map((item) => item.id)) }} className="h-10 rounded-md border border-[#d9d9d9] bg-white px-4 text-sm text-[#333] hover:bg-[#f7f7f7]">
                取消
              </button>
              <button type="button" onClick={saveOrder} disabled={reorderMutation.isPending} className="h-10 rounded-md bg-[#1a1a1a] px-4 text-sm font-medium text-white hover:bg-black disabled:opacity-50">
                确定
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setSorting(true)} className="h-10 rounded-md border border-[#d9d9d9] bg-white px-4 text-sm font-medium text-[#1a1a1a] hover:bg-[#f7f7f7]">
              排序
            </button>
          )}
          <button
            type="button"
            onClick={() => router.push('/ticket-workflows/new')}
            className="flex h-10 items-center gap-2 rounded-md bg-[#1a1a1a] px-5 text-sm font-medium text-white hover:bg-black"
          >
            <IconPlus size={16} />
            新建流程
          </button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-[#e5e5e5] py-24">
          <p className="text-sm text-muted-foreground">暂无工单流程</p>
          <button
            type="button"
            onClick={() => router.push('/ticket-workflows/new')}
            className="flex h-10 items-center gap-2 rounded-md bg-[#1a1a1a] px-5 text-sm font-medium text-white"
          >
            <IconPlus size={16} />
            新建流程
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#e5e5e5] bg-white">
          <div className="flex h-12 items-center border-b border-[#e5e5e5] bg-[#f7f7f7] px-6 text-sm font-semibold text-[#333]">
            <div className="w-24 shrink-0">序号</div>
            <div className="min-w-0 flex-1">名称</div>
            <div className="w-[280px] shrink-0">生效时机</div>
            <div className="w-[180px] shrink-0">启用</div>
            <div className="w-[120px] shrink-0 text-center">操作</div>
          </div>
          {rows.map((row, index) => (
            <div
              key={row.id}
              className="flex h-14 items-center border-t border-[#e5e5e5] px-6 first:border-t-0 hover:bg-[#fafafa]"
              onDragOver={(event) => sorting && event.preventDefault()}
              onDrop={() => sorting && handleDrop(index)}
            >
              <div className="flex w-24 shrink-0 items-center text-sm text-[#333]">
                {sorting ? (
                  <button
                    type="button"
                    draggable
                    onDragStart={() => setDragIndex(index)}
                    onDragEnd={() => setDragIndex(null)}
                    className="flex cursor-grab items-center gap-2 text-muted-foreground active:cursor-grabbing"
                    aria-label={`拖拽排序 ${row.name}`}
                  >
                    <IconGripVertical size={16} />
                    <span>{index + 1}</span>
                  </button>
                ) : (
                  index + 1
                )}
              </div>
              <div className="min-w-0 flex-1 truncate text-sm font-medium text-[#1a1a1a]">{row.name}</div>
              <div className="w-[280px] shrink-0 text-sm text-[#333]">{eventSummary(row.trigger_event_types)}</div>
              <div className="w-[180px] shrink-0">
                <Switch
                  checked={row.enabled}
                  onCheckedChange={(checked) => updateMutation.mutate({ id: row.id, data: { enabled: checked } })}
                />
              </div>
              <div className="flex w-[120px] shrink-0 items-center justify-center gap-4">
                <button type="button" onClick={() => router.push(`/ticket-workflows/${row.id}`)} className="text-[#333] hover:text-[#111]" aria-label="编辑">
                  <IconPencil size={18} />
                </button>
                <button type="button" onClick={() => setDeleteTarget(row)} className="text-[#333] hover:text-destructive" aria-label="删除">
                  <IconTrash size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-[420px] rounded-lg bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-foreground">删除流程</h2>
            <p className="mt-3 text-sm text-muted-foreground">确定删除以下工单流程？删除后不可恢复。</p>
            <div className="mt-3 rounded-md border border-border p-3 text-sm font-medium">{deleteTarget.name}</div>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => setDeleteTarget(null)} className="h-9 rounded-md border border-border px-4 text-sm hover:bg-muted">
                取消
              </button>
              <button
                type="button"
                disabled={deleteMutation.isPending}
                onClick={async () => {
                  await deleteMutation.mutateAsync(deleteTarget.id)
                  setDeleteTarget(null)
                }}
                className="h-9 rounded-md bg-destructive px-4 text-sm font-medium text-white disabled:opacity-50"
              >
                确定删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
