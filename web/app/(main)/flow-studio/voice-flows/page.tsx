'use client'

import { useState } from 'react'
import Link from 'next/link'
import { IconPencil, IconTrash } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { FlowStudioTabs } from '@/app/components/features/flow-studio-tabs'
import { useVoiceFlows, useDeleteVoiceFlow } from '@/service/use-voice-flows'
import type { VoiceFlowListItem } from '@/models/voice-flow'

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: VoiceFlowListItem
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('vf.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('vf.delete.confirm', locale, { name: item.name })}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('vf.delete.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('vf.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function VoiceFlowsListPage() {
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const perPage = 20
  const { data, isLoading } = useVoiceFlows({ page, per_page: perPage })
  const deleteMut = useDeleteVoiceFlow()
  const [deleteTarget, setDeleteTarget] = useState<VoiceFlowListItem | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMut.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      setToast({ type: 'success', text: t('vf.deleteSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('vf.deleteFailed', locale) })
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

      <FlowStudioTabs active="voice-flows" />

      <div className="flex justify-end">
        <Link
          href="/flow-studio/voice-flows/new"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-9 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white hover:bg-primary/80"
        >
          {t('vf.new', locale)}
        </Link>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('vf.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('vf.empty', locale)}</p>
          <Link
            href="/flow-studio/voice-flows/new"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-9 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            {t('vf.new', locale)}
          </Link>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-12 items-center gap-4 border-b border-border bg-muted px-4 text-sm font-semibold text-foreground/80">
              <div className="flex-1">{t('vf.col.name', locale)}</div>
              <div className="w-[240px] truncate">描述</div>
              <div className="w-[180px]">最后更新</div>
              <div className="w-24 text-center">{t('vf.col.enabled', locale)}</div>
              <div className="w-[90px] text-center">{t('vf.col.actions', locale)}</div>
            </div>
            {items.map((row) => (
              <div
                key={row.id}
                className="flex h-14 items-center gap-4 border-t border-border px-4 first:border-t-0"
              >
                <div className="flex-1 truncate text-sm text-foreground">{row.name}</div>
                <div className="w-[240px] truncate text-sm text-muted-foreground">
                  {row.description || '—'}
                </div>
                <div className="w-[180px] text-sm text-muted-foreground">
                  {formatDate(row.updated_at)}
                </div>
                <div className="w-24 text-center text-sm text-muted-foreground">
                  {row.enabled ? (locale === 'zh' ? '是' : 'Yes') : locale === 'zh' ? '否' : 'No'}
                </div>
                <div className="flex w-[90px] items-center justify-center gap-3">
                  <Link
                    href={`/flow-studio/voice-flows/${row.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label={t('vf.action.edit', locale)}
                  >
                    <IconPencil size={18} />
                  </Link>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(row)}
                    className="text-foreground/80 transition-colors hover:text-red-600"
                    aria-label={t('vf.action.delete', locale)}
                  >
                    <IconTrash size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('vf.pagination.total', locale, { total: String(total) })}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 rounded-md border border-border px-3 text-sm text-foreground/80 disabled:opacity-40"
              >
                {t('vf.pagination.prev', locale)}
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
                {t('vf.pagination.next', locale)}
              </button>
            </div>
          </div>
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
