'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconCopy, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useChannels, useCopyChannel, useDeleteChannel } from '@/service/use-channels'
import type { Channel } from '@/models/channel'

function formatDate(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: Channel
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('ch.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('ch.delete.confirm', locale, { name: item.name })}
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
            {t('ch.delete.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('ch.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

function CopyModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: Channel
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('ch.copy.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('ch.copy.confirm', locale)}
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
            {t('ch.copy.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
          >
            {loading ? '...' : t('ch.copy.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ChannelWebListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading } = useChannels()
  const deleteMut = useDeleteChannel()
  const copyMut = useCopyChannel()

  const items = (data ?? []) as Channel[]

  const [deleteTarget, setDeleteTarget] = useState<Channel | null>(null)
  const [copyTarget, setCopyTarget] = useState<Channel | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMut.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', t('ch.deleteSuccess', locale))
    } catch {
      showToast('error', t('ch.deleteFailed', locale))
    }
  }

  const handleCopy = async () => {
    if (!copyTarget) return
    try {
      await copyMut.mutateAsync(copyTarget.id)
      setCopyTarget(null)
      showToast('success', t('ch.copySuccess', locale))
    } catch {
      showToast('error', t('ch.copyFailed', locale))
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

      {/* Page header: title 24px/700 + button with plus icon */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">{t('ch.title', locale)}</h1>
        <button
          type="button"
          onClick={() => router.push('/channels/web/new')}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/80"
        >
          <IconPlus size={16} />
          {t('ch.new', locale)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('ch.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('ch.empty', locale)}</p>
          <button
            type="button"
            onClick={() => router.push('/channels/web/new')}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white"
          >
            <IconPlus size={16} />
            {t('ch.new', locale)}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          {/* Table header — match session-routing list frame */}
          <div className="flex h-12 items-center gap-6 rounded-t-lg border-b border-border bg-muted px-6 text-sm font-semibold text-foreground/80">
            <div className="min-w-0 flex-1">{t('ch.col.name', locale)}</div>
            <div className="w-[160px] shrink-0">{t('ch.col.updatedAt', locale)}</div>
            <div className="w-[120px] shrink-0">{t('ch.col.actions', locale)}</div>
          </div>
          {/* Data rows: h-14 (56px), border-bottom */}
          {items.map((row) => (
            <div
              key={row.id}
              className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
            >
              <div className="min-w-0 flex-1 truncate text-sm text-foreground">{row.name}</div>
              <div className="w-[160px] shrink-0 text-sm text-muted-foreground">
                {formatDate(row.updated_at)}
              </div>
              <div className="flex w-[120px] shrink-0 items-center gap-4">
                <button
                  type="button"
                  onClick={() => router.push(`/channels/web/${row.id}`)}
                  className="text-foreground/80 transition-colors hover:text-foreground"
                  aria-label={t('ch.action.edit', locale)}
                >
                  <IconPencil size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => setCopyTarget(row)}
                  className="text-foreground/80 transition-colors hover:text-foreground"
                  aria-label={t('ch.action.copy', locale)}
                >
                  <IconCopy size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(row)}
                  className="text-foreground/80 transition-colors hover:text-destructive"
                  aria-label={t('ch.action.delete', locale)}
                >
                  <IconTrash size={18} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {copyTarget && (
        <CopyModal
          item={copyTarget}
          onCancel={() => setCopyTarget(null)}
          onConfirm={handleCopy}
          loading={copyMut.isPending}
        />
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
