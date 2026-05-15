'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconPencil, IconTrash, IconPlus } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useServiceHours, useDeleteServiceHours } from '@/service/use-service-hours'
import type { ServiceHours } from '@/models/service-hours'

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: ServiceHours
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">
          {t('sh.delete.title', locale)}
        </h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('sh.delete.confirm', locale)}
        </p>
        <div className="mt-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium text-foreground">{item.name}</p>
          {item.description && (
            <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
          )}
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            {t('sh.delete.cancel', locale)}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('sh.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ServiceHoursListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading } = useServiceHours()
  const deleteMutation = useDeleteServiceHours()
  const [deleteTarget, setDeleteTarget] = useState<ServiceHours | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      setToast({ type: 'success', text: t('sh.deleteSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('sh.deleteFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-xl font-semibold text-foreground">{t('sh.title', locale)}</h1>
        <p className="text-sm text-muted-foreground">{t('sh.loading', locale)}</p>
      </div>
    )
  }

  const items = data ?? []

  return (
    <div className="flex flex-col gap-6">
      {toast && (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'bg-green-50 text-green-700'
              : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('sh.title', locale)}</h1>
        <button
          onClick={() => router.push('/service-hours/new')}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('sh.new', locale)}
        </button>
      </div>

      {items.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('sh.empty', locale)}</p>
          <button
            onClick={() => router.push('/service-hours/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('sh.new', locale)}
          </button>
        </div>
      ) : (
        /* Table */
        <div className="overflow-hidden rounded-lg border border-border">
          {/* Table header */}
          <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
            <div className="flex flex-1 items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('sh.col.name', locale)}</span>
            </div>
            <div className="flex w-[200px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('sh.col.updatedAt', locale)}</span>
            </div>
            <div className="flex w-[100px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('sh.col.actions', locale)}</span>
            </div>
          </div>

          {/* Table rows */}
          {items.map((item) => (
            <div
              key={item.id}
              className="flex h-14 items-center gap-6 border-t border-border px-6"
            >
              <div className="flex flex-1 items-center">
                <span className="text-sm text-foreground">{item.name}</span>
              </div>
              <div className="flex w-[200px] items-center">
                <span className="text-sm text-muted-foreground">
                  {item.updated_at ? formatDate(item.updated_at) : '-'}
                </span>
              </div>
              <div className="flex w-[100px] items-center gap-4">
                <button
                  onClick={() => router.push(`/service-hours/${item.id}`)}
                  className="text-foreground/80 transition-colors hover:text-foreground"
                >
                  <IconPencil size={18} />
                </button>
                <button
                  onClick={() => setDeleteTarget(item)}
                  className="text-foreground/80 transition-colors hover:text-destructive"
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
          loading={deleteMutation.isPending}
        />
      )}
    </div>
  )
}
