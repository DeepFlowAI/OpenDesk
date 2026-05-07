'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconGripVertical, IconPencil, IconTrash } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { FlowStudioTabs } from '@/app/components/features/flow-studio-tabs'
import {
  useInboundRoutingRules,
  useDeleteInboundRoutingRule,
  useReorderInboundRoutingRules,
} from '@/service/use-inbound-routing-rules'
import type { InboundRoutingRuleListItem } from '@/models/inbound-routing-rule'

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: InboundRoutingRuleListItem
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('rr.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('rr.delete.confirm', locale, { name: item.name })}
        </p>
        <div className="mt-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium text-foreground">{item.name}</p>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('rr.delete.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('rr.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function RoutingRulesListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const perPage = 100
  const { data, isLoading, refetch } = useInboundRoutingRules({ page, per_page: perPage })
  const deleteMut = useDeleteInboundRoutingRule()
  const reorderMut = useReorderInboundRoutingRules()

  const items = useMemo(() => data?.items ?? [], [data?.items])
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  const [orderedIds, setOrderedIds] = useState<number[]>([])
  useEffect(() => {
    setOrderedIds(items.map((i) => i.id))
  }, [items])

  const byId = useMemo(() => Object.fromEntries(items.map((i) => [i.id, i])), [items])
  const displayRows = orderedIds.map((id) => byId[id]).filter(Boolean) as InboundRoutingRuleListItem[]

  const [deleteTarget, setDeleteTarget] = useState<InboundRoutingRuleListItem | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const handleDrop = async (toIndex: number) => {
    if (dragIndex == null || dragIndex === toIndex) {
      setDragIndex(null)
      return
    }
    const next = [...orderedIds]
    const [removed] = next.splice(dragIndex, 1)
    next.splice(toIndex, 0, removed)
    setOrderedIds(next)
    setDragIndex(null)
    try {
      await reorderMut.mutateAsync(next)
    } catch {
      setToast({ type: 'error', text: t('rr.reorderFailed', locale) })
      setTimeout(() => setToast(null), 3000)
      refetch()
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMut.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      setToast({ type: 'success', text: t('rr.deleteSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('rr.deleteFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <FlowStudioTabs active="routing-rules" />

      <div className="flex items-center justify-between">
        <div />
        <button
          type="button"
          onClick={() => router.push('/flow-studio/routing-rules/new')}
          className="h-10 rounded-lg bg-primary px-5 text-sm font-medium text-white hover:bg-primary/80"
        >
          {t('rr.new', locale)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('rr.loading', locale)}</p>
      ) : displayRows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('rr.empty', locale)}</p>
          <button
            type="button"
            onClick={() => router.push('/flow-studio/routing-rules/new')}
            className="h-10 rounded-lg bg-primary px-5 text-sm font-medium text-white"
          >
            {t('rr.new', locale)}
          </button>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            {/* Table header — design: h-56, px-24, gap-24, bg-#F8F8F8, top-corners 8px */}
            <div className="flex h-14 items-center gap-6 rounded-t-lg border-b border-border bg-muted px-6 text-sm font-semibold text-foreground/80">
              <div className="w-6 shrink-0" />
              <div className="w-20 shrink-0">{t('rr.col.priority', locale)}</div>
              <div className="min-w-0 flex-1">{t('rr.col.name', locale)}</div>
              <div className="w-[200px] shrink-0">{t('rr.col.flow', locale)}</div>
              <div className="w-[100px] shrink-0">{t('rr.col.enabled', locale)}</div>
              <div className="w-[90px] shrink-0 text-center">{t('rr.col.actions', locale)}</div>
            </div>
            {displayRows.map((row, idx) => (
              <div
                key={row.id}
                className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleDrop(idx)}
              >
                <div
                  className="flex w-6 shrink-0 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
                  draggable
                  onDragStart={() => setDragIndex(idx)}
                  onDragEnd={() => setDragIndex(null)}
                >
                  <IconGripVertical size={16} />
                </div>
                <div className="w-20 shrink-0 text-sm text-foreground">{row.priority}</div>
                <div className="min-w-0 flex-1 truncate text-sm text-foreground">{row.name}</div>
                <div className="w-[200px] shrink-0 truncate text-sm text-foreground">
                  {row.target_flow_name || '—'}
                </div>
                <div className="w-[100px] shrink-0 text-sm text-muted-foreground">
                  {row.enabled ? t('rr.status.enabled', locale) : t('rr.status.disabled', locale)}
                </div>
                <div className="flex w-[90px] shrink-0 items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => router.push(`/flow-studio/routing-rules/${row.id}`)}
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label={t('rr.action.edit', locale)}
                  >
                    <IconPencil size={18} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(row)}
                    className="text-foreground/80 transition-colors hover:text-red-600"
                    aria-label={t('rr.action.delete', locale)}
                  >
                    <IconTrash size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          {pages > 1 && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {t('rr.pagination.total', locale, { total: String(total) })}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="h-8 rounded-md border border-border px-3 text-sm text-foreground/80 disabled:opacity-40"
                >
                  {t('rr.pagination.prev', locale)}
                </button>
                <span className="text-sm text-foreground/80">
                  {page} / {pages || 1}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(pages || 1, p + 1))}
                  disabled={page >= (pages || 1)}
                  className="h-8 rounded-md border border-border px-3 text-sm text-foreground/80 disabled:opacity-40"
                >
                  {t('rr.pagination.next', locale)}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {deleteTarget && (
        <DeleteModal
          item={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteMut.isPending}
        />
      )}
    </div>
  )
}
