'use client'

import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconEye,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { useDeleteRole, useRoles, type RoleListParams } from '@/service/use-roles'
import type { Role } from '@/models/role'
import { cn } from '@/lib/utils'

function ConfirmModal({
  role,
  loading,
  onCancel,
  onConfirm,
}: {
  role: Role
  loading: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{t('role.delete.title', locale)}</h2>
        <p className="mt-3 text-sm text-muted-foreground">
          {t('role.delete.confirm', locale, { name: role.name })}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            {t('role.delete.cancel', locale)}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : t('role.delete.ok', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

function SimpleSelect({
  value,
  options,
  onChange,
}: {
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((option) => option.value === value)
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-9 min-w-[120px] items-center justify-between gap-2 rounded-lg border border-border px-3 text-sm text-foreground/80"
      >
        <span>{selected?.label ?? value}</span>
        <IconChevronDown size={16} className="text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute left-0 top-10 z-20 w-full rounded-lg border border-border bg-white py-1 shadow-lg">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value)
                setOpen(false)
              }}
              className={cn(
                'block w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent',
                option.value === value ? 'font-medium text-foreground' : 'text-foreground/80'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function TypeBadge({ role }: { role: Role }) {
  const { locale } = useLocaleStore()
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium',
        role.is_system ? 'bg-muted text-foreground' : 'bg-info/10 text-info'
      )}
    >
      {role.is_system ? t('role.type.system', locale) : t('role.type.custom', locale)}
    </span>
  )
}

function StatusBadge({ active }: { active: boolean }) {
  const { locale } = useLocaleStore()
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium',
        active ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive/80'
      )}
    >
      {active ? t('role.status.active', locale) : t('role.status.inactive', locale)}
    </span>
  )
}

export default function RolesListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const deleteMutation = useDeleteRole()
  const [keyword, setKeyword] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [page, setPage] = useState(1)
  const perPage = 10
  const [appliedParams, setAppliedParams] = useState<RoleListParams>({ page: 1, per_page: perPage })
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const { data, isLoading } = useRoles(appliedParams)

  const showToast = useCallback((type: 'success' | 'error', key: string) => {
    setToast({ type, text: t(key, locale) })
    setTimeout(() => setToast(null), 3000)
  }, [locale])

  const handleSearch = useCallback(() => {
    const params: RoleListParams = { page: 1, per_page: perPage }
    if (keyword.trim()) params.keyword = keyword.trim()
    if (typeFilter) params.type = typeFilter
    setPage(1)
    setAppliedParams(params)
  }, [keyword, typeFilter])

  const handleReset = useCallback(() => {
    setKeyword('')
    setTypeFilter('')
    setPage(1)
    setAppliedParams({ page: 1, per_page: perPage })
  }, [])

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', 'role.deleteSuccess')
    } catch {
      showToast('error', 'role.deleteFailed')
    }
  }

  const handlePageChange = (nextPage: number) => {
    setPage(nextPage)
    setAppliedParams((prev) => ({ ...prev, page: nextPage }))
  }

  const typeOptions = [
    { value: '', label: t('role.filter.all', locale) },
    { value: 'system', label: t('role.type.system', locale) },
    { value: 'custom', label: t('role.type.custom', locale) },
  ]
  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0
  const canManage = hasPermission(user, 'org.role.manage')

  return (
    <div className="flex flex-col gap-6">
      {toast && (
        <div
          className={cn(
            'rounded-lg px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {toast.text}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('role.title', locale)}</h1>
        {canManage && (
          <button
            onClick={() => router.push('/roles/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            {t('role.new', locale)}
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-9 w-[280px] items-center gap-2 rounded-lg border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            type="text"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') handleSearch()
            }}
            placeholder={t('role.filter.keyword', locale)}
            className="flex-1 border-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
          />
        </div>
        <span className="text-sm font-medium text-foreground/80">{t('role.filter.type', locale)}</span>
        <SimpleSelect value={typeFilter} options={typeOptions} onChange={setTypeFilter} />
        <button
          onClick={handleSearch}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          {t('role.filter.query', locale)}
        </button>
        <button
          onClick={handleReset}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {t('role.filter.reset', locale)}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('role.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('role.empty', locale)}</p>
          {canManage && (
            <button
              onClick={() => router.push('/roles/new')}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
            >
              <IconPlus size={18} />
              {t('role.new', locale)}
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <div style={{ minWidth: 940 }}>
              <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
                <div className="w-[160px] shrink-0 text-sm font-semibold text-foreground/80">{t('role.col.name', locale)}</div>
                <div className="min-w-[220px] flex-1 text-sm font-semibold text-foreground/80">{t('role.col.description', locale)}</div>
                <div className="w-[90px] shrink-0 text-sm font-semibold text-foreground/80">{t('role.col.type', locale)}</div>
                <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">{t('role.col.status', locale)}</div>
                <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">{t('role.col.members', locale)}</div>
                <div className="w-[150px] shrink-0 text-sm font-semibold text-foreground/80">{t('role.col.updatedAt', locale)}</div>
                {canManage && (
                  <div className="w-[96px] shrink-0 text-right text-sm font-semibold text-foreground/80">{t('role.col.actions', locale)}</div>
                )}
              </div>
              {items.map((role) => (
                <div key={role.id} className="flex h-14 items-center gap-6 border-t border-border px-6">
                  <div className="w-[160px] shrink-0 truncate text-sm font-medium text-foreground">{role.name}</div>
                  <div className="min-w-[220px] flex-1 truncate text-sm text-muted-foreground">{role.description || '-'}</div>
                  <div className="w-[90px] shrink-0"><TypeBadge role={role} /></div>
                  <div className="w-[80px] shrink-0"><StatusBadge active={role.is_active} /></div>
                  <div className="w-[100px] shrink-0 text-sm text-muted-foreground">{role.member_count}</div>
                  <div className="w-[150px] shrink-0 truncate text-sm text-muted-foreground">
                    {role.updated_at ? new Date(role.updated_at).toLocaleString() : '-'}
                  </div>
                  {canManage && (
                    <div className="flex w-[96px] shrink-0 items-center justify-end gap-3">
                      <button
                        title={t(role.is_system ? 'role.action.view' : 'role.action.edit', locale)}
                        onClick={() => router.push(`/roles/${role.id}`)}
                        className="text-foreground/80 transition-colors hover:text-foreground"
                      >
                        {role.is_system ? <IconEye size={18} /> : <IconPencil size={18} />}
                      </button>
                      <button
                        title={t('role.action.copy', locale)}
                        onClick={() => router.push(`/roles/new?copyFrom=${role.id}`)}
                        className="text-foreground/80 transition-colors hover:text-foreground"
                      >
                        <IconCopy size={18} />
                      </button>
                      {!role.is_system && role.member_count === 0 && (
                        <button
                          title={t('role.action.delete', locale)}
                          onClick={() => setDeleteTarget(role)}
                          className="text-foreground/80 transition-colors hover:text-destructive"
                        >
                          <IconTrash size={18} />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('role.pagination.total', locale, { total })}
            </span>
            <div className="flex items-center gap-1">
              <button
                disabled={page <= 1}
                onClick={() => handlePageChange(page - 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border transition-colors hover:bg-accent disabled:opacity-40"
              >
                <IconChevronLeft size={16} />
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map((item) => (
                <button
                  key={item}
                  onClick={() => handlePageChange(item)}
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-lg text-sm transition-colors',
                    item === page ? 'bg-primary text-white' : 'text-foreground/80 hover:bg-accent'
                  )}
                >
                  {item}
                </button>
              ))}
              <button
                disabled={page >= pages}
                onClick={() => handlePageChange(page + 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border transition-colors hover:bg-accent disabled:opacity-40"
              >
                <IconChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      )}

      {canManage && deleteTarget && (
        <ConfirmModal
          role={deleteTarget}
          loading={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
    </div>
  )
}
