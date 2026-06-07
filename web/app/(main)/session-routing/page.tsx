'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconGripVertical, IconPencil, IconTrash, IconPlus } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Switch } from '@/components/ui/switch'
import {
  useSessionRoutingRules,
  useDeleteSessionRoutingRule,
  useReorderSessionRoutingRules,
  usePatchSessionRoutingRuleEnabled,
} from '@/service/use-session-routing-rules'
import type { SessionRoutingRuleListItem } from '@/models/session-routing-rule'

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: SessionRoutingRuleListItem
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('sr.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('sr.delete.confirm', locale, { name: item.name })}
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
            {t('sr.delete.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('sr.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function SessionRoutingPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const perPage = 100
  const { data, isLoading, refetch } = useSessionRoutingRules({ page: 1, per_page: perPage })
  const deleteMut = useDeleteSessionRoutingRule()
  const reorderMut = useReorderSessionRoutingRules()
  const patchEnabledMut = usePatchSessionRoutingRuleEnabled()

  const items = useMemo(() => data?.items ?? [], [data?.items])

  const [orderedIds, setOrderedIds] = useState<number[]>([])
  useEffect(() => {
    setOrderedIds(items.map((i) => i.id))
  }, [items])

  const byId = useMemo(() => Object.fromEntries(items.map((i) => [i.id, i])), [items])
  const displayRows = orderedIds.map((id) => byId[id]).filter(Boolean) as SessionRoutingRuleListItem[]

  const [deleteTarget, setDeleteTarget] = useState<SessionRoutingRuleListItem | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

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
      showToast('error', t('sr.reorderFailed', locale))
      refetch()
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMut.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', t('sr.deleteSuccess', locale))
    } catch {
      showToast('error', t('sr.deleteFailed', locale))
    }
  }

  const handleToggleEnabled = async (item: SessionRoutingRuleListItem) => {
    try {
      await patchEnabledMut.mutateAsync({ id: item.id, enabled: !item.enabled })
    } catch {
      showToast('error', t('sr.toggleFailed', locale))
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

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">{t('sr.title', locale)}</h1>
        <button
          type="button"
          onClick={() => router.push('/session-routing/new')}
          className="flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('sr.new', locale)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('sr.loading', locale)}</p>
      ) : displayRows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('sr.empty', locale)}</p>
          <button
            type="button"
            onClick={() => router.push('/session-routing/new')}
            className="flex h-10 items-center gap-2 rounded-lg bg-primary px-5 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('sr.new', locale)}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          {/* Table header */}
          <div className="flex h-12 items-center gap-6 rounded-t-lg border-b border-border bg-muted px-6 text-sm font-semibold text-foreground/80">
            <div className="w-8 shrink-0" />
            <div className="w-[72px] shrink-0">{t('sr.col.priority', locale)}</div>
            <div className="min-w-0 flex-1">{t('sr.col.name', locale)}</div>
            <div className="w-[280px] shrink-0">{t('sr.col.target', locale)}</div>
            <div className="w-[100px] shrink-0">{t('sr.col.enabled', locale)}</div>
            <div className="w-[80px] shrink-0 text-center">{t('sr.col.actions', locale)}</div>
          </div>
          {displayRows.map((row, idx) => (
            <div
              key={row.id}
              className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => handleDrop(idx)}
            >
              <div
                className="flex w-8 shrink-0 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
                draggable
                onDragStart={() => setDragIndex(idx)}
                onDragEnd={() => setDragIndex(null)}
              >
                <IconGripVertical size={16} />
              </div>
              <div className="w-[72px] shrink-0 text-sm text-foreground">{row.priority}</div>
              <div className="min-w-0 flex-1 truncate text-sm text-foreground">{row.name}</div>
              <div className="w-[280px] shrink-0 truncate text-sm text-foreground">
                {row.target_summary || row.target_group_name || '—'}
              </div>
              <div className="w-[100px] shrink-0">
                <Switch
                  checked={row.enabled}
                  onCheckedChange={() => handleToggleEnabled(row)}
                />
              </div>
              <div className="flex w-[80px] shrink-0 items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={() => router.push(`/session-routing/${row.id}`)}
                  className="text-foreground/80 transition-colors hover:text-foreground"
                  aria-label={t('sr.action.edit', locale)}
                >
                  <IconPencil size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(row)}
                  className="text-foreground/80 transition-colors hover:text-red-600"
                  aria-label={t('sr.action.delete', locale)}
                >
                  <IconTrash size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
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
