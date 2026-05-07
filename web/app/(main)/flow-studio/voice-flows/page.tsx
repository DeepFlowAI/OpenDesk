'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
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

export default function VoiceFlowsListPage() {
  const router = useRouter()
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
        <button
          type="button"
          onClick={() => router.push('/flow-studio/voice-flows/new')}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white hover:bg-primary/80"
        >
          {t('vf.new', locale)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('vf.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('vf.empty', locale)}</p>
          <button
            type="button"
            onClick={() => router.push('/flow-studio/voice-flows/new')}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            {t('vf.new', locale)}
          </button>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-12 items-center gap-4 border-b border-border bg-muted px-4 text-sm font-semibold text-foreground/80">
              <div className="flex-1">{t('vf.col.name', locale)}</div>
              <div className="w-24 text-center">{t('vf.col.enabled', locale)}</div>
              <div className="w-28 text-right">{t('vf.col.actions', locale)}</div>
            </div>
            {items.map((row) => (
              <div
                key={row.id}
                className="flex h-14 items-center gap-4 border-t border-border px-4 first:border-t-0"
              >
                <div className="flex-1 truncate text-sm text-foreground">{row.name}</div>
                <div className="w-24 text-center text-sm text-muted-foreground">
                  {row.enabled ? (locale === 'zh' ? '是' : 'Yes') : locale === 'zh' ? '否' : 'No'}
                </div>
                <div className="flex w-28 justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => router.push(`/flow-studio/voice-flows/${row.id}`)}
                    className="text-sm text-foreground/80 hover:text-foreground"
                  >
                    {t('vf.action.edit', locale)}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(row)}
                    className="text-sm text-foreground/80 hover:text-red-600"
                  >
                    {t('vf.action.delete', locale)}
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
