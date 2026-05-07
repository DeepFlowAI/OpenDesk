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
  useUnifiedFields,
  useUpdateFieldDefinition,
  useUpdateSystemFieldOverride,
  useDeleteFieldDefinition,
  useSortFieldDefinitions,
} from '@/service/use-field-definitions'
import {
  FieldSource,
  FIELD_TYPE_LABELS,
  FIELD_SOURCE_LABELS,
} from '@/types/field-enums'
import type { UnifiedField } from '@/models/field-definition'
import type { FieldType as FieldTypeEnum } from '@/types/field-enums'

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

function SourceBadge({ source, locale }: { source: string; locale: 'zh' | 'en' }) {
  const label = FIELD_SOURCE_LABELS[source as keyof typeof FIELD_SOURCE_LABELS]?.[locale] ?? source
  const isSystem = source === FieldSource.SYSTEM
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${
        isSystem ? 'bg-muted text-foreground' : 'bg-info/10 text-info'
      }`}
    >
      {label}
    </span>
  )
}

function StatusBadge({ status, locale }: { status: string; locale: 'zh' | 'en' }) {
  const isActive = status === 'active'
  const label = isActive ? t('of.status.active', locale) : t('of.status.inactive', locale)
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

function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'bg-primary' : 'bg-input'
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
          checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
        }`}
      />
    </button>
  )
}

function fieldUid(field: UnifiedField): string {
  return field.key ? `sys_${field.key}` : `cus_${field.id}`
}

export default function OrganizationFieldsListPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const deleteMutation = useDeleteFieldDefinition()
  const updateMutation = useUpdateFieldDefinition()
  const overrideMutation = useUpdateSystemFieldOverride()
  const sortMutation = useSortFieldDefinitions()

  const { data, isLoading } = useUnifiedFields({ domain: 'organization', locale })

  const [sortMode, setSortMode] = useState(false)
  const [sortItems, setSortItems] = useState<UnifiedField[]>([])
  const originalOrderRef = useRef<UnifiedField[]>([])

  const [deleteTarget, setDeleteTarget] = useState<UnifiedField | null>(null)
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
        domain: 'organization',
        data: {
          items: sortItems.map((item, idx) => ({
            id: item.id ?? undefined,
            key: item.key ?? undefined,
            sort_order: idx + 1,
          })),
        },
      })
      setSortMode(false)
      setSortItems([])
      showToast('success', 'of.sortSuccess')
    } catch {
      showToast('error', 'of.sortFailed')
    }
  }, [sortItems, sortMutation, showToast])

  const sortItemIds = useMemo(() => sortItems.map(fieldUid), [sortItems])

  const handleToggleWorkspace = useCallback(
    async (field: UnifiedField) => {
      try {
        if (field.source === 'system' && field.key) {
          await overrideMutation.mutateAsync({
            domain: 'organization',
            fieldKey: field.key,
            data: { show_in_workspace: !field.show_in_workspace },
          })
        } else if (field.id) {
          await updateMutation.mutateAsync({
            id: field.id,
            data: { show_in_workspace: !field.show_in_workspace },
          })
        }
      } catch {
        showToast('error', 'of.saveFailed')
      }
    },
    [updateMutation, overrideMutation, showToast],
  )

  const handleDelete = useCallback(async () => {
    if (!deleteTarget || !deleteTarget.id) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', 'of.deleteSuccess')
    } catch {
      showToast('error', 'of.deleteFailed')
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

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('of.title', locale)}</h1>
        <div className="flex items-center gap-3">
          {sortMode ? (
            <>
              <button
                onClick={handleCancelSort}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
              >
                {t('of.sortCancel', locale)}
              </button>
              <button
                onClick={handleConfirmSort}
                disabled={sortMutation.isPending}
                className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
              >
                {sortMutation.isPending ? '...' : t('of.sortConfirm', locale)}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEnterSortMode}
                disabled={items.length === 0}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {t('of.sort', locale)}
              </button>
              <button
                onClick={() => router.push('/organization-fields/custom/new')}
                className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
              >
                <IconPlus size={18} />
                {t('of.newCustomField', locale)}
              </button>
            </>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('of.loading', locale)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <p className="text-sm text-muted-foreground">{t('of.empty', locale)}</p>
          <button
            onClick={() => router.push('/organization-fields/custom/new')}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('of.newCustomField', locale)}
          </button>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <div style={{ minWidth: 900 }}>
              <div className="flex h-14 items-center gap-4 rounded-t-lg bg-muted px-6">
                <div className="w-12 shrink-0 text-sm font-semibold text-foreground/80">
                  {sortMode ? '' : t('of.col.index', locale)}
                </div>
                <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('of.col.name', locale)}
                </div>
                <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('of.col.source', locale)}
                </div>
                <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('of.col.type', locale)}
                </div>
                <div className="w-[100px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('of.col.showInWorkspace', locale)}
                </div>
                <div className="w-[60px] shrink-0 text-sm font-semibold text-foreground/80">
                  {t('of.col.status', locale)}
                </div>
                <div className="min-w-[140px] flex-1 text-sm font-semibold text-foreground/80">
                  {t('of.col.updatedAt', locale)}
                </div>
                <div className="w-[80px] shrink-0 text-right text-sm font-semibold text-foreground/80">
                  {t('of.col.actions', locale)}
                </div>
              </div>

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
                    const uid = fieldUid(field)
                    return (
                      <SortableFieldTableRow
                        key={uid}
                        id={uid}
                        className="flex h-14 items-center gap-4 border-t border-border px-6"
                        dragCell={(drag) => <DefaultSortDragHandle {...drag} />}
                      >
                        <div className="w-[140px] shrink-0 truncate text-sm text-foreground">
                          {field.name}
                        </div>
                        <div className="w-[80px] shrink-0">
                          <SourceBadge source={field.source} locale={locale} />
                        </div>
                        <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                          {typeLabel}
                        </div>
                        <div className="w-[100px] shrink-0">
                          <ToggleSwitch
                            checked={field.show_in_workspace ?? false}
                            onChange={() => handleToggleWorkspace(field)}
                            disabled
                          />
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
                  const isCustom = field.source === 'custom'
                  const typeLabel =
                    FIELD_TYPE_LABELS[field.field_type as FieldTypeEnum]?.[locale] ?? field.field_type

                  return (
                    <div
                      key={fieldUid(field)}
                      className="flex h-14 items-center gap-4 border-t border-border px-6"
                    >
                      <div className="w-12 shrink-0">
                        <span className="text-sm text-muted-foreground">{idx + 1}</span>
                      </div>
                      <div className="w-[140px] shrink-0 truncate text-sm text-foreground">
                        {field.name}
                      </div>
                      <div className="w-[80px] shrink-0">
                        <SourceBadge source={field.source} locale={locale} />
                      </div>
                      <div className="w-[100px] shrink-0 truncate text-sm text-muted-foreground">
                        {typeLabel}
                      </div>
                      <div className="w-[100px] shrink-0">
                        <ToggleSwitch
                          checked={field.show_in_workspace ?? false}
                          onChange={() => handleToggleWorkspace(field)}
                          disabled={false}
                        />
                      </div>
                      <div className="w-[60px] shrink-0">
                        <StatusBadge status={field.status} locale={locale} />
                      </div>
                      <div className="min-w-[140px] flex-1 truncate text-sm text-muted-foreground">
                        {formatDate(field.updated_at)}
                      </div>
                      <div className="flex w-[80px] shrink-0 items-center justify-end gap-3">
                        {isCustom && field.id && (
                          <>
                            <button
                              onClick={() => router.push(`/organization-fields/custom/${field.id}`)}
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
                          </>
                        )}
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
                {t('of.pagination.total', locale, { total })}
              </span>
            </div>
          )}
        </>
      )}

      {deleteTarget && (
        <ConfirmModal
          title={t('of.delete.title', locale)}
          message={t('of.delete.confirm', locale, { name: deleteTarget.name })}
          confirmText={t('of.delete.ok', locale)}
          cancelText={t('of.delete.cancel', locale)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteMutation.isPending}
        />
      )}
    </div>
  )
}
