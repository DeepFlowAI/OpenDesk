'use client'

import { useState, useCallback, useRef, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { arrayMove } from '@dnd-kit/sortable'
import { IconPlus, IconPencil, IconTrash } from '@tabler/icons-react'
import {
  SortableFieldRowsContext,
  SortableFieldTableRow,
  DefaultSortDragHandle,
} from '@/components/admin/sortable-field-table'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useFieldDefinitions,
  useDeleteFieldDefinition,
  useSortFieldDefinitions,
} from '@/service/use-field-definitions'
import {
  FIELD_TYPE_LABELS,
  APPLICABLE_MODULE_LABELS,
} from '@/types/field-enums'
import type { FieldType as FieldTypeEnum, ApplicableModule } from '@/types/field-enums'
import type { FdFieldDefinition } from '@/models/field-definition'

function ConfirmModal({
  title,
  message,
  confirmText,
  cancelText,
  onCancel,
  onConfirm,
  loading,
}: {
  title: string
  message: string
  confirmText: string
  cancelText: string
  onCancel: () => void
  onConfirm: () => void
  loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[420px] rounded-xl bg-white p-6">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <p className="mt-3 text-sm text-muted-foreground whitespace-pre-line">{message}</p>
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
            className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80 disabled:opacity-50"
          >
            {loading ? '...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status, locale }: { status: string; locale: 'zh' | 'en' }) {
  const isActive = status === 'active'
  const label = isActive ? t('sf.status.active', locale) : t('sf.status.inactive', locale)
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
        isActive ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive/80'
      }`}
    >
      {label}
    </span>
  )
}

function ModuleTags({ modules, locale }: { modules: string[] | null; locale: 'zh' | 'en' }) {
  if (!modules || modules.length === 0) return <span className="text-sm text-muted-foreground">-</span>
  return (
    <div className="flex flex-wrap gap-1">
      {modules.map((m) => {
        const label =
          APPLICABLE_MODULE_LABELS[m as ApplicableModule]?.[locale] ?? m
        return (
          <span
            key={m}
            className="inline-flex items-center rounded bg-muted px-2 py-0.5 text-xs font-medium text-foreground/80"
          >
            {label}
          </span>
        )
      })}
    </div>
  )
}

function poolFieldSortId(field: FdFieldDefinition): string {
  return String(field.id)
}

export default function SharedFieldsListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const deleteMutation = useDeleteFieldDefinition()
  const sortMutation = useSortFieldDefinitions()

  const { data, isLoading } = useFieldDefinitions({ domain: 'shared_pool' })

  const [sortMode, setSortMode] = useState(false)
  const [sortItems, setSortItems] = useState<FdFieldDefinition[]>([])
  const originalOrderRef = useRef<FdFieldDefinition[]>([])

  const [deleteTarget, setDeleteTarget] = useState<FdFieldDefinition | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const showToast = useCallback(
    (type: 'success' | 'error', key: string) => {
      setToast({ type, text: t(key, locale) })
      setTimeout(() => setToast(null), 3000)
    },
    [locale],
  )

  const items = sortMode ? sortItems : (data?.items ?? [])
  const total = data?.total ?? 0

  const handleEnterSortMode = useCallback(() => {
    const current = data?.items ?? []
    originalOrderRef.current = current
    setSortItems([...current])
    setSortMode(true)
  }, [data])

  const handleCancelSort = useCallback(() => {
    setSortMode(false)
    setSortItems([])
  }, [])

  const handleConfirmSort = useCallback(async () => {
    try {
      await sortMutation.mutateAsync({
        domain: 'shared_pool',
        data: {
          items: sortItems.map((item, idx) => ({
            id: item.id,
            sort_order: idx + 1,
          })),
        },
      })
      setSortMode(false)
      setSortItems([])
      showToast('success', 'sf.sortSuccess')
    } catch {
      showToast('error', 'sf.sortFailed')
    }
  }, [sortItems, sortMutation, showToast])

  const sortItemIds = useMemo(() => sortItems.map(poolFieldSortId), [sortItems])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', 'sf.deleteSuccess')
    } catch {
      showToast('error', 'sf.deleteFailed')
    }
  }, [deleteTarget, deleteMutation, showToast])

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
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
        <h1 className="text-xl font-semibold text-foreground">{t('sf.title', locale)}</h1>
        <div className="flex items-center gap-3">
          {sortMode ? (
            <>
              <button
                onClick={handleCancelSort}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
              >
                {t('sf.sortCancel', locale)}
              </button>
              <button
                onClick={handleConfirmSort}
                disabled={sortMutation.isPending}
                className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
              >
                {sortMutation.isPending ? '...' : t('sf.sortConfirm', locale)}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEnterSortMode}
                disabled={items.length === 0}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {t('sf.sort', locale)}
              </button>
              <button
                onClick={() => router.push('/shared-fields/custom/new')}
                className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
              >
                <IconPlus size={18} />
                {t('sf.newCustomField', locale)}
              </button>
            </>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('sf.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('sf.empty', locale)}</p>
          <button
            onClick={() => router.push('/shared-fields/custom/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('sf.newCustomField', locale)}
          </button>
        </div>
      ) : (
        <>
          {/* Table */}
          <div className="overflow-x-auto rounded-lg border border-border">
            <div style={{ minWidth: 900 }}>
              {/* Header */}
              <div className="flex h-14 items-center gap-4 rounded-t-lg bg-muted px-6">
                <div className="w-12 shrink-0 text-sm font-semibold text-foreground/80">
                  {sortMode ? '' : t('sf.col.index', locale)}
                </div>
                <div className="w-[160px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('sf.col.name', locale)}
                </div>
                <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('sf.col.type', locale)}
                </div>
                <div className="w-[200px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('sf.col.applicableModules', locale)}
                </div>
                <div className="w-[60px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('sf.col.status', locale)}
                </div>
                <div className="min-w-[140px] flex-1 text-sm font-semibold text-foreground/80">
                  {t('sf.col.updatedAt', locale)}
                </div>
                <div className="w-[80px] shrink-0 text-right text-sm font-semibold text-foreground/80">
                  {t('sf.col.actions', locale)}
                </div>
              </div>

              {/* Rows */}
              {sortMode ? (
                <SortableFieldRowsContext
                  itemIds={sortItemIds}
                  onReorderIndices={(from, to) =>
                    setSortItems((prev) => arrayMove(prev, from, to))
                  }
                >
                  {sortItems.map((field) => {
                    const typeLabel =
                      FIELD_TYPE_LABELS[field.field_type as FieldTypeEnum]?.[locale] ?? field.field_type
                    const sid = poolFieldSortId(field)
                    return (
                      <SortableFieldTableRow
                        key={sid}
                        id={sid}
                        className="flex h-14 items-center gap-4 border-t border-border px-6"
                        dragCell={(drag) => <DefaultSortDragHandle {...drag} />}
                      >
                        <div className="w-[160px] shrink-0 truncate text-sm text-foreground">
                          {field.name}
                        </div>
                        <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                          {typeLabel}
                        </div>
                        <div className="w-[200px] shrink-0">
                          <ModuleTags modules={field.applicable_modules} locale={locale} />
                        </div>
                        <div className="w-[60px] shrink-0">
                          <StatusBadge status={field.status} locale={locale} />
                        </div>
                        <div className="min-w-[140px] flex-1 truncate text-sm text-muted-foreground">
                          {formatDate(field.updated_at)}
                        </div>
                        <div className="flex w-[80px] shrink-0 items-center justify-end gap-3" />
                      </SortableFieldTableRow>
                    )
                  })}
                </SortableFieldRowsContext>
              ) : (
                items.map((field, idx) => {
                  const typeLabel =
                    FIELD_TYPE_LABELS[field.field_type as FieldTypeEnum]?.[locale] ?? field.field_type

                  return (
                    <div
                      key={field.id}
                      className="flex h-14 items-center gap-4 border-t border-border px-6"
                    >
                      <div className="w-12 shrink-0">
                        <span className="text-sm text-muted-foreground">{idx + 1}</span>
                      </div>
                      <div className="w-[160px] shrink-0 truncate text-sm text-foreground">
                        {field.name}
                      </div>
                      <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                        {typeLabel}
                      </div>
                      <div className="w-[200px] shrink-0">
                        <ModuleTags modules={field.applicable_modules} locale={locale} />
                      </div>
                      <div className="w-[60px] shrink-0">
                        <StatusBadge status={field.status} locale={locale} />
                      </div>
                      <div className="min-w-[140px] flex-1 truncate text-sm text-muted-foreground">
                        {formatDate(field.updated_at)}
                      </div>
                      <div className="flex w-[80px] shrink-0 items-center justify-end gap-3">
                        <button
                          onClick={() => router.push(`/shared-fields/custom/${field.id}`)}
                          className="text-foreground/80 transition-colors hover:text-foreground"
                        >
                          <IconPencil size={18} />
                        </button>
                        <button
                          onClick={() => setDeleteTarget(field)}
                          className="text-foreground/80 transition-colors hover:text-destructive"
                        >
                          <IconTrash size={18} />
                        </button>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {!sortMode && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {t('sf.pagination.total', locale, { total })}
              </span>
            </div>
          )}
        </>
      )}

      {deleteTarget && (
        <ConfirmModal
          title={t('sf.delete.title', locale)}
          message={t('sf.delete.confirm', locale, { name: deleteTarget.name })}
          confirmText={t('sf.delete.ok', locale)}
          cancelText={t('sf.delete.cancel', locale)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteMutation.isPending}
        />
      )}
    </div>
  )
}
