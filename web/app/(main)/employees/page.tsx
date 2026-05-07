'use client'

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { IconPencil, IconTrash, IconPlus, IconSearch, IconChevronDown, IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useEmployees, useDeleteEmployee, useUpdateEmployeeStatus } from '@/service/use-employees'
import type { Employee } from '@/models/employee'
import type { EmployeeListParams } from '@/service/use-employees'

function ConfirmModal({
  title,
  message,
  confirmText,
  cancelText,
  onCancel,
  onConfirm,
  loading,
  destructive = false,
}: {
  title: string
  message: string
  confirmText: string
  cancelText: string
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
  destructive?: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="mt-3 text-sm text-muted-foreground">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`h-9 rounded-lg px-4 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
              destructive
                ? 'bg-destructive hover:bg-destructive/80'
                : 'bg-primary hover:bg-primary/80'
            }`}
          >
            {loading ? '...' : confirmText}
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
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-9 items-center justify-between gap-2 rounded-lg border border-border px-3 text-sm text-foreground/80"
        style={{ minWidth: 100 }}
      >
        <span>{selected?.label ?? value}</span>
        <IconChevronDown size={16} className="text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute top-10 left-0 z-20 w-full rounded-lg border border-border bg-white py-1 shadow-lg">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`block w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent ${
                opt.value === value ? 'font-medium text-foreground' : 'text-foreground/80'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function RoleMultiSelect({
  value,
  options,
  onChange,
  locale,
}: {
  value: string[]
  options: { value: string; label: string }[]
  onChange: (v: string[]) => void
  locale: 'zh' | 'en'
}) {
  const [open, setOpen] = useState(false)

  const toggle = (v: string) => {
    if (value.includes(v)) onChange(value.filter((x) => x !== v))
    else onChange([...value, v])
  }

  const summary =
    value.length === 0
      ? t('emp.filter.all', locale)
      : options
          .filter((o) => value.includes(o.value))
          .map((o) => o.label)
          .join(locale === 'zh' ? '、' : ', ')

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-9 max-w-[220px] items-center justify-between gap-2 rounded-lg border border-border px-3 text-sm text-foreground/80"
        style={{ minWidth: 140 }}
      >
        <span className="truncate">{summary}</span>
        <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute top-10 left-0 z-20 min-w-full rounded-lg border border-border bg-white py-1 shadow-lg">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggle(opt.value)}
              className={`block w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent ${
                value.includes(opt.value) ? 'font-medium text-foreground' : 'text-foreground/80'
              }`}
            >
              {value.includes(opt.value) ? '✓ ' : ''}
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function RoleBadge({ role, locale }: { role: string; locale: 'zh' | 'en' }) {
  const label = role === 'admin' ? t('emp.role.admin', locale) : t('emp.role.agent', locale)
  const bg = role === 'admin' ? 'bg-muted text-foreground' : 'bg-info/10 text-info'
  return <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${bg}`}>{label}</span>
}

function RoleBadges({ roles, locale }: { roles: string[]; locale: 'zh' | 'en' }) {
  return (
    <div className="flex flex-wrap gap-1">
      {roles.map((role) => (
        <RoleBadge key={role} role={role} locale={locale} />
      ))}
    </div>
  )
}

function StatusBadge({ active, locale }: { active: boolean; locale: 'zh' | 'en' }) {
  const label = active ? t('emp.status.active', locale) : t('emp.status.inactive', locale)
  const bg = active ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive/80'
  return <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${bg}`}>{label}</span>
}

function AvatarCell({ employee }: { employee: Employee }) {
  if (employee.avatar) {
    return (
      <img
        src={employee.avatar}
        alt={employee.name}
        className="h-9 w-9 rounded-full object-cover"
      />
    )
  }
  const initial = employee.name.charAt(0).toUpperCase()
  return (
    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-border text-sm font-medium text-muted-foreground">
      {initial}
    </div>
  )
}

export default function EmployeesListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const deleteMutation = useDeleteEmployee()
  const statusMutation = useUpdateEmployeeStatus()

  const [keyword, setKeyword] = useState('')
  const [roleFilter, setRoleFilter] = useState<string[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const perPage = 10

  const [appliedParams, setAppliedParams] = useState<EmployeeListParams>({
    page: 1,
    per_page: perPage,
  })

  const { data, isLoading } = useEmployees(appliedParams)

  const [deleteTarget, setDeleteTarget] = useState<Employee | null>(null)
  const [statusTarget, setStatusTarget] = useState<Employee | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const showToast = useCallback((type: 'success' | 'error', key: string) => {
    setToast({ type, text: t(key, locale) })
    setTimeout(() => setToast(null), 3000)
  }, [locale])

  const handleSearch = useCallback(() => {
    const params: EmployeeListParams = { page: 1, per_page: perPage }
    if (keyword.trim()) params.keyword = keyword.trim()
    if (roleFilter.length > 0) params.role = roleFilter
    if (statusFilter) params.status = statusFilter
    setPage(1)
    setAppliedParams(params)
  }, [keyword, roleFilter, statusFilter])

  const handleReset = useCallback(() => {
    setKeyword('')
    setRoleFilter([])
    setStatusFilter('')
    setPage(1)
    setAppliedParams({ page: 1, per_page: perPage })
  }, [])

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
    setAppliedParams((prev) => ({ ...prev, page: newPage }))
  }, [])

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', 'emp.deleteSuccess')
    } catch {
      showToast('error', 'emp.deleteFailed')
    }
  }

  const handleStatusToggle = async () => {
    if (!statusTarget) return
    try {
      await statusMutation.mutateAsync({
        id: statusTarget.id,
        data: { is_active: !statusTarget.is_active },
      })
      setStatusTarget(null)
      showToast('success', 'emp.statusSuccess')
    } catch {
      showToast('error', 'emp.statusFailed')
    }
  }

  const roleFilterOptions = [
    { value: 'admin', label: t('emp.role.admin', locale) },
    { value: 'agent', label: t('emp.role.agent', locale) },
  ]

  const statusOptions = [
    { value: '', label: t('emp.filter.all', locale) },
    { value: 'active', label: t('emp.status.active', locale) },
    { value: 'inactive', label: t('emp.status.inactive', locale) },
  ]

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

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

      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('emp.title', locale)}</h1>
        <button
          onClick={() => router.push('/employees/new')}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={18} />
          {t('emp.new', locale)}
        </button>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex h-9 items-center gap-2 rounded-lg border border-border px-3" style={{ width: 280 }}>
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
            placeholder={t('emp.filter.keyword', locale)}
            className="flex-1 border-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
          />
        </div>
        <span className="text-sm font-medium text-foreground/80">{t('emp.filter.role', locale)}</span>
        <RoleMultiSelect value={roleFilter} options={roleFilterOptions} onChange={setRoleFilter} locale={locale} />
        <span className="text-sm font-medium text-foreground/80">{t('emp.filter.status', locale)}</span>
        <SimpleSelect value={statusFilter} options={statusOptions} onChange={setStatusFilter} />
        <button
          onClick={handleSearch}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          {t('emp.filter.query', locale)}
        </button>
        <button
          onClick={handleReset}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          {t('emp.filter.reset', locale)}
        </button>
      </div>

      {/* Loading */}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('emp.loading', locale)}</p>
      ) : items.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('emp.empty', locale)}</p>
          <button
            onClick={() => router.push('/employees/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('emp.new', locale)}
          </button>
        </div>
      ) : (
        <>
          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-border">
            <div style={{ minWidth: 1000 }}>
              {/* Table header */}
              <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
                <div className="w-9 shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.avatar', locale)}</span></div>
                <div className="w-[100px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.name', locale)}</span></div>
                <div className="w-[80px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.nickname', locale)}</span></div>
                <div className="w-[70px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.jobNumber', locale)}</span></div>
                <div className="w-[100px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.username', locale)}</span></div>
                <div className="min-w-[160px] flex-1"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.email', locale)}</span></div>
                <div className="w-[110px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.phone', locale)}</span></div>
                <div className="w-[120px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.role', locale)}</span></div>
                <div className="w-[60px] shrink-0"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.status', locale)}</span></div>
                <div className="w-[120px] shrink-0 text-right"><span className="text-sm font-semibold text-foreground/80">{t('emp.col.actions', locale)}</span></div>
              </div>

              {/* Table rows */}
              {items.map((emp) => (
                <div
                  key={emp.id}
                  className="flex h-14 items-center gap-6 border-t border-border px-6"
                >
                  <div className="w-9 shrink-0"><AvatarCell employee={emp} /></div>
                  <div className="w-[100px] shrink-0 truncate text-sm text-foreground">{emp.name}</div>
                  <div className="w-[80px] shrink-0 truncate text-sm text-muted-foreground">{emp.nickname ?? '-'}</div>
                  <div className="w-[70px] shrink-0 truncate text-sm text-muted-foreground">{emp.job_number ?? '-'}</div>
                  <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">{emp.username}</div>
                  <div className="min-w-[160px] flex-1 truncate text-sm text-muted-foreground">{emp.email ?? '-'}</div>
                  <div className="w-[110px] shrink-0 truncate text-sm text-muted-foreground">{emp.phone ?? '-'}</div>
                  <div className="w-[120px] shrink-0"><RoleBadges roles={emp.roles} locale={locale} /></div>
                  <div className="w-[60px] shrink-0"><StatusBadge active={emp.is_active} locale={locale} /></div>
                  <div className="flex w-[120px] shrink-0 items-center justify-end gap-3">
                    <button
                      onClick={() => router.push(`/employees/${emp.id}`)}
                      className="text-sm text-foreground/80 transition-colors hover:text-foreground"
                    >
                      <IconPencil size={18} />
                    </button>
                    <button
                      onClick={() => setStatusTarget(emp)}
                      className="text-sm text-foreground/80 transition-colors hover:text-foreground"
                    >
                      {emp.is_active ? t('emp.action.disable', locale) : t('emp.action.enable', locale)}
                    </button>
                    {!emp.is_super_admin && (
                      <button
                        onClick={() => setDeleteTarget(emp)}
                        className="text-foreground/80 transition-colors hover:text-destructive"
                      >
                        <IconTrash size={18} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {t('emp.pagination.total', locale, { total })}
            </span>
            <div className="flex items-center gap-1">
              <button
                disabled={page <= 1}
                onClick={() => handlePageChange(page - 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-border transition-colors hover:bg-accent disabled:opacity-40"
              >
                <IconChevronLeft size={16} />
              </button>
              {Array.from({ length: pages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => handlePageChange(p)}
                  className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm transition-colors ${
                    p === page
                      ? 'bg-primary text-white'
                      : 'hover:bg-accent text-foreground/80'
                  }`}
                >
                  {p}
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

      {/* Delete confirm modal */}
      {deleteTarget && (
        <ConfirmModal
          title={t('emp.delete.title', locale)}
          message={t('emp.delete.confirm', locale, { name: deleteTarget.name })}
          confirmText={t('emp.delete.ok', locale)}
          cancelText={t('emp.delete.cancel', locale)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteMutation.isPending}
          destructive
        />
      )}

      {/* Status toggle confirm modal */}
      {statusTarget && (
        <ConfirmModal
          title={t('emp.status.title', locale)}
          message={
            statusTarget.is_active
              ? t('emp.status.disableConfirm', locale, { name: statusTarget.name })
              : t('emp.status.enableConfirm', locale, { name: statusTarget.name })
          }
          confirmText={statusTarget.is_active ? t('emp.action.disable', locale) : t('emp.action.enable', locale)}
          cancelText={t('emp.delete.cancel', locale)}
          onCancel={() => setStatusTarget(null)}
          onConfirm={handleStatusToggle}
          loading={statusMutation.isPending}
        />
      )}
    </div>
  )
}
