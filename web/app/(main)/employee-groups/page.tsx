'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconPencil, IconTrash, IconPlus } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useEmployeeGroups, useDeleteEmployeeGroup } from '@/service/use-employee-groups'
import type { EmployeeGroupListItem } from '@/models/employee-group'

function DeleteModal({
  item,
  onCancel,
  onConfirm,
  loading,
}: {
  item: EmployeeGroupListItem
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">
          {t('eg.delete.title', locale)}
        </h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('eg.delete.confirm', locale, { name: item.name })}
        </p>
        <div className="mt-3 rounded-lg border border-border p-3">
          <p className="text-sm font-medium text-foreground">{item.name}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {item.description || '—'}
          </p>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            {t('eg.delete.cancel', locale)}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('eg.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function EmployeeGroupsPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const perPage = 10

  const { data, isLoading } = useEmployeeGroups({ page, per_page: perPage, keyword: searchKeyword || undefined })
  const deleteMutation = useDeleteEmployeeGroup()
  const [deleteTarget, setDeleteTarget] = useState<EmployeeGroupListItem | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleSearch = () => {
    setSearchKeyword(keyword)
    setPage(1)
  }

  const handleReset = () => {
    setKeyword('')
    setSearchKeyword('')
    setPage(1)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      setToast({ type: 'success', text: t('eg.deleteSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('eg.deleteFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-xl font-semibold text-foreground">{t('eg.title', locale)}</h1>
        <p className="text-sm text-muted-foreground">{t('eg.loading', locale)}</p>
      </div>
    )
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0
  const canManage = hasPermission(user, 'org.group.manage')

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

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('eg.title', locale)}</h1>
        {canManage && (
          <button
            onClick={() => router.push('/employee-groups/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            {t('eg.new', locale)}
          </button>
        )}
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-4">
        <input
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder={t('eg.search.placeholder', locale)}
          className="h-9 w-64 rounded-lg border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          onClick={handleSearch}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          {t('eg.search', locale)}
        </button>
        <button
          onClick={handleReset}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {t('eg.reset', locale)}
        </button>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('eg.empty', locale)}</p>
          {canManage && (
            <button
              onClick={() => router.push('/employee-groups/new')}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
            >
              <IconPlus size={18} />
              {t('eg.new', locale)}
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Table */}
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
              <div className="flex w-[220px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">{t('eg.col.name', locale)}</span>
              </div>
              <div className="flex min-w-0 flex-1 items-center">
                <span className="text-sm font-semibold text-foreground/80">{t('eg.col.desc', locale)}</span>
              </div>
              <div className="flex w-[80px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">{t('eg.col.memberCount', locale)}</span>
              </div>
              {canManage && (
                <div className="flex w-[70px] shrink-0 items-center">
                  <span className="text-sm font-semibold text-foreground/80">{t('eg.col.actions', locale)}</span>
                </div>
              )}
            </div>

            {items.map((item) => (
              <div
                key={item.id}
                className="flex h-14 items-center gap-6 border-t border-border px-6"
              >
                <div className="flex w-[220px] shrink-0 items-center">
                  <span className="truncate text-sm text-foreground" title={item.name}>
                    {item.name}
                  </span>
                </div>
                <div className="flex min-w-0 flex-1 items-center">
                  <span className="truncate text-sm text-muted-foreground" title={item.description || undefined}>
                    {item.description || '—'}
                  </span>
                </div>
                <div className="flex w-[80px] shrink-0 items-center">
                  <span className="text-sm text-muted-foreground">{item.member_count}</span>
                </div>
                {canManage && (
                  <div className="flex w-[70px] shrink-0 items-center gap-3">
                    <button
                      onClick={() => router.push(`/employee-groups/${item.id}`)}
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
                )}
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('eg.pagination.total', locale, { total: String(total) })}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-8 rounded-md border border-border px-3 text-sm text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {t('eg.pagination.prev', locale)}
              </button>
              <span className="text-sm text-foreground/80">
                {page} / {pages || 1}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page >= pages}
                className="h-8 rounded-md border border-border px-3 text-sm text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {t('eg.pagination.next', locale)}
              </button>
            </div>
          </div>
        </>
      )}

      {canManage && deleteTarget && (
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
