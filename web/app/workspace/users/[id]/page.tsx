'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconEdit,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { useDeleteUser, useUser } from '@/service/use-users'
import { useOrganization } from '@/service/use-organizations'
import { useSystemSettings } from '@/service/use-system-settings'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'
import type { UnifiedField } from '@/models/field-definition'
import { FieldType } from '@/types/field-enums'
import {
  FieldValueDisplay,
  formatActorFieldValue,
} from '@/app/components/features/field-system/field-value-display'
import { UserRelatedTimeline } from '@/app/components/features/user-related-timeline'
import { UserFormModal } from '../user-form-modal'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { hasPermission } from '@/utils/permissions'

const SYSTEM_KEY_ALIAS: Record<string, string> = { nickname: 'name' }
const DATETIME_KEYS = new Set(['created_at', 'updated_at'])
const SYSTEM_INFO_SYSTEM_KEYS = new Set(['public_id', 'created_by', 'updated_by'])
const GENDER_LABELS: Record<string, { zh: string; en: string }> = {
  male: { zh: '男', en: 'Male' },
  female: { zh: '女', en: 'Female' },
  unknown: { zh: '未知', en: 'Unknown' },
  other: { zh: '其他', en: 'Other' },
}
const SELECT_TYPES = new Set(['single_select', 'multi_select', 'single_select_tree', 'multi_select_tree'])

export default function UserDetailPage() {
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const router = useRouter()
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const isZh = locale === 'zh'
  const canEditUser = hasPermission(currentUser, 'crm.workspace.user.edit')
  const canDeleteUser = hasPermission(currentUser, 'crm.workspace.user.delete')

  const userRef = params.id
  const fromList = searchParams.get('from') === 'list'

  const { data: user, isLoading, error } = useUser(userRef)
  const { data: systemSettings } = useSystemSettings()
  const organizationEnabled = systemSettings?.organization_enabled === true
  const { data: organization, isLoading: organizationLoading } = useOrganization(
    user?.organization_id ?? 0,
    organizationEnabled,
  )
  const { data: fieldsData } = useUnifiedFields({ domain: 'user', include_metadata: true })

  const allFields: UnifiedField[] = useMemo(() => fieldsData?.items ?? [], [fieldsData])
  const fieldDefMap = useMemo(() => {
    const m = new Map<string, UnifiedField>()
    for (const f of allFields) {
      if (f.id != null) m.set(String(f.id), f)
      if (f.key) m.set(f.key, f)
      if (f.key === 'nickname') m.set('name', f)
      if (f.slot_column) m.set(f.slot_column, f)
    }
    return m
  }, [allFields])

  const systemFields = useMemo(
    () => allFields.filter((f) => f.source === 'system'),
    [allFields],
  )
  const basicSystemFields = useMemo(
    () => systemFields.filter((f) => !SYSTEM_INFO_SYSTEM_KEYS.has(f.key ?? '')),
    [systemFields],
  )
  const visibleBasicSystemFields = useMemo(
    () =>
      organizationEnabled
        ? basicSystemFields
        : basicSystemFields.filter((f) => f.key !== 'organization_id'),
    [basicSystemFields, organizationEnabled],
  )
  const customFields = useMemo(
    () => allFields.filter((f) => f.source === 'custom' && f.status === 'active'),
    [allFields],
  )
  const metadataFields = useMemo(
    () => allFields.filter((f) => f.source === 'metadata'),
    [allFields],
  )
  const systemInfoFields = useMemo(
    () => [
      ...systemFields.filter((f) => SYSTEM_INFO_SYSTEM_KEYS.has(f.key ?? '')),
      ...metadataFields,
    ],
    [systemFields, metadataFields],
  )
  const hasOrganizationSystemField = useMemo(
    () => organizationEnabled && systemFields.some((f) => f.key === 'organization_id'),
    [systemFields, organizationEnabled],
  )

  const [editModalOpen, setEditModalOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const deleteMutation = useDeleteUser()

  useEffect(() => {
    if (!user?.public_id || !userRef || !/^\d+$/.test(userRef)) return
    const qs = searchParams.toString()
    router.replace(`/workspace/users/${user.public_id}${qs ? `?${qs}` : ''}`)
  }, [router, searchParams, user?.public_id, userRef])

  const handleEditSuccess = useCallback(() => {
    setEditModalOpen(false)
  }, [])

  const handleDelete = useCallback(async () => {
    if (!user) return
    try {
      await deleteMutation.mutateAsync(user.id)
      toast.success(isZh ? '删除成功' : 'Deleted successfully')
      router.push('/workspace/users')
    } catch {
      toast.error(isZh ? '删除失败，请重试' : 'Delete failed. Please try again.')
    }
  }, [deleteMutation, isZh, router, user])

  const getFieldRaw = useCallback(
    (field: UnifiedField): unknown => {
      if (!user) return undefined
      const key = field.key
      if (key && field.source !== 'custom') {
        const realKey = SYSTEM_KEY_ALIAS[key] ?? key
        return (user as Record<string, unknown>)[realKey]
      }
      if (key && user.custom_fields) {
        return user.custom_fields[key] ?? (field.id != null ? user.custom_fields[String(field.id)] : undefined)
      }
      if (field.id != null && user.custom_fields) {
        return user.custom_fields[String(field.id)]
      }
      return undefined
    },
    [user],
  )

  const getFieldValue = useCallback(
    (field: UnifiedField): string => {
      if (!user) return ''
      const key = field.key
      if (key && field.source !== 'custom') {
        const realKey = SYSTEM_KEY_ALIAS[key] ?? key
        const raw = (user as Record<string, unknown>)[realKey]
        if (raw == null) return '—'
        if (field.type_config?.value_kind === 'actor') return formatActorFieldValue(raw)
        if (DATETIME_KEYS.has(key)) return new Date(raw as string).toLocaleString()

        if (key === 'gender') {
          const g = GENDER_LABELS[String(raw)]
          return g ? (isZh ? g.zh : g.en) : String(raw)
        }

        if (SELECT_TYPES.has(field.field_type)) {
          return resolveSelectValue(String(raw), field)
        }
        return String(raw)
      }
      if (user.custom_fields) {
        const val = key && user.custom_fields[key] != null
          ? user.custom_fields[key]
          : field.id != null
            ? user.custom_fields[String(field.id)]
            : null
        if (val == null) return '—'
        const str = Array.isArray(val) ? val.join(',') : String(val)
        if (field.field_type === FieldType.DATETIME) {
          return formatDatetimeForDisplay(str)
        }
        if (SELECT_TYPES.has(field.field_type)) {
          return resolveSelectValue(str, field)
        }
        return str
      }
      return '—'
    },
    [user, isZh],
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{isZh ? '加载中...' : 'Loading...'}</p>
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-muted-foreground">
          {isZh ? '用户不存在或无权限访问' : 'User not found or access denied'}
        </p>
        <button
          onClick={() => router.push('/workspace/users')}
          className="text-sm font-medium text-primary hover:underline"
        >
          {isZh ? '返回用户列表' : 'Back to user list'}
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      {/* Top bar */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-white px-6 py-3">
        {fromList && (
          <button
            onClick={() => router.push('/workspace/users')}
            className="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            {isZh ? '返回列表' : 'Back to list'}
          </button>
        )}
        <h2 className="flex-1 text-base font-semibold text-foreground">{user.name}</h2>
        {canEditUser && (
          <button
            onClick={() => setEditModalOpen(true)}
            className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconEdit size={16} />
            {isZh ? '编辑用户' : 'Edit User'}
          </button>
        )}
        {canDeleteUser && (
          <button
            onClick={() => setDeleteConfirmOpen(true)}
            disabled={deleteMutation.isPending}
            className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
          >
            <IconTrash size={16} />
            {isZh ? '删除' : 'Delete'}
          </button>
        )}
      </div>

      {/* Main content: left profile + right timeline */}
      <div className="flex min-h-0 flex-1 overflow-hidden bg-white">
        {/* Left: Profile panel (info card keeps tinted surface) */}
        <div className="w-[32rem] shrink-0 overflow-y-auto bg-white p-6">
          <div className="rounded-xl border border-border bg-accent/50 p-5">
            {/* Basic info section */}
            <h3 className="mb-3 text-sm font-semibold text-foreground">
              {isZh ? '基本信息' : 'Basic Info'}
            </h3>
            <div className="flex flex-col gap-2.5">
              {visibleBasicSystemFields.map((f) => (
                <div key={f.key ?? f.id} className="flex items-start gap-3">
                  <span className="w-20 shrink-0 text-sm text-muted-foreground">{f.name}</span>
                  {f.key === 'organization_id' ? (
                    user.organization_id && organization ? (
                      <button
                        type="button"
                        className="min-w-0 flex-1 break-words text-left text-sm font-medium text-primary outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => router.push(`/workspace/organizations/${organization.public_id || user.organization_id}`)}
                        aria-label={
                          isZh
                            ? `查看组织 ${organization.name}`
                            : `View organization ${organization.name}`
                        }
                      >
                        {organization.name}
                      </button>
                    ) : (
                      <span className="min-w-0 flex-1 break-words text-sm text-foreground">
                        {organizationLoading ? (isZh ? '加载中...' : 'Loading...') : '—'}
                      </span>
                    )
                  ) : f.field_type === FieldType.URL ? (
                    <div className="min-w-0 flex-1 text-sm">
                      <FieldValueDisplay fieldType={FieldType.URL} value={getFieldRaw(f)} />
                    </div>
                  ) : (
                    <span className="min-w-0 flex-1 break-words text-sm text-foreground">
                      {getFieldValue(f)}
                    </span>
                  )}
                </div>
              ))}
              {organizationEnabled && !hasOrganizationSystemField && (
                <div className="flex items-start gap-3">
                  <span className="w-20 shrink-0 text-sm text-muted-foreground">
                    {isZh ? '组织' : 'Organization'}
                  </span>
                  {user.organization_id && organization ? (
                    <button
                      type="button"
                      className="min-w-0 flex-1 break-words text-left text-sm font-medium text-primary outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => router.push(`/workspace/organizations/${organization.public_id || user.organization_id}`)}
                      aria-label={
                        isZh
                          ? `查看组织 ${organization.name}`
                          : `View organization ${organization.name}`
                      }
                    >
                      {organization.name}
                    </button>
                  ) : (
                    <span className="min-w-0 flex-1 break-words text-sm text-foreground">
                      {organizationLoading ? (isZh ? '加载中...' : 'Loading...') : '—'}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Custom fields section */}
            {customFields.length > 0 && (
              <>
                <h3 className="mb-3 mt-6 text-sm font-semibold text-foreground">
                  {isZh ? '自定义字段' : 'Custom Fields'}
                </h3>
                <div className="flex flex-col gap-2.5">
                  {customFields.map((f) => {
                    const raw =
                      user.custom_fields
                        ? f.key && user.custom_fields[f.key] != null
                          ? user.custom_fields[f.key]
                          : f.id != null
                            ? user.custom_fields[String(f.id)]
                            : undefined
                        : undefined
                    return (
                      <div key={f.id} className="flex items-start gap-3">
                        <span className="w-20 shrink-0 text-sm text-muted-foreground">{f.name}</span>
                        <div className="min-w-0 flex-1 break-words text-sm text-foreground">
                          {f.field_type === FieldType.FILE ? (
                            <FieldValueDisplay
                              fieldType={FieldType.FILE}
                              value={raw}
                              typeConfig={(f.type_config ?? {}) as Record<string, unknown>}
                            />
                          ) : f.field_type === FieldType.RICH_TEXT ? (
                            <FieldValueDisplay
                              fieldType={FieldType.RICH_TEXT}
                              value={raw}
                              typeConfig={(f.type_config ?? {}) as Record<string, unknown>}
                            />
                          ) : f.field_type === FieldType.URL ? (
                            <FieldValueDisplay fieldType={FieldType.URL} value={raw} />
                          ) : (
                            getFieldValue(f)
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </>
            )}

            {/* System info section */}
            {systemInfoFields.length > 0 && (
              <>
                <h3 className="mb-3 mt-6 text-sm font-semibold text-foreground">
                  {isZh ? '系统信息' : 'System Info'}
                </h3>
                <div className="flex flex-col gap-2.5">
                  {systemInfoFields.map((f) => (
                    <div key={f.key ?? f.id} className="flex items-start gap-3">
                      <span className="w-20 shrink-0 text-sm text-muted-foreground">{f.name}</span>
                      {f.field_type === FieldType.URL ? (
                        <div className="min-w-0 flex-1 text-sm">
                          <FieldValueDisplay fieldType={FieldType.URL} value={getFieldRaw(f)} />
                        </div>
                      ) : (
                        <span className="min-w-0 flex-1 break-words text-sm text-foreground">
                          {getFieldValue(f)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        <UserRelatedTimeline
          userId={user.id}
          isZh={isZh}
          resolveFieldDef={(fieldKey) => fieldDefMap.get(fieldKey)}
        />
      </div>

      {/* Edit modal */}
      {canEditUser && editModalOpen && (
        <UserFormModal
          mode="edit"
          user={user}
          onClose={() => setEditModalOpen(false)}
          onSuccess={handleEditSuccess}
        />
      )}

      {canDeleteUser && (
        <ConfirmDialog
          open={deleteConfirmOpen}
        title={isZh ? '删除用户' : 'Delete user'}
        message={
          isZh
            ? '确定要删除以下用户吗？此操作不可撤销。'
            : 'Are you sure you want to delete this user? This action cannot be undone.'
        }
        itemName={user.name}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        cancelLabel={isZh ? '取消' : 'Cancel'}
        variant="destructive"
        loading={deleteMutation.isPending}
        onCancel={() => setDeleteConfirmOpen(false)}
          onConfirm={handleDelete}
        />
      )}
    </div>
  )
}

function resolveSelectValue(raw: string, field: UnifiedField): string {
  const valueMap = new Map<string, string>()

  if (field.options?.length) {
    for (const o of field.options) {
      if (o.is_active) valueMap.set(o.value, o.label)
    }
  }
  if (field.tree_nodes?.length) {
    for (const n of field.tree_nodes) {
      if (n.is_active) valueMap.set(n.value, n.label)
    }
  }
  const cfgOpts = (field.type_config as { options?: { label: string; value: string }[] })?.options
  if (cfgOpts) {
    for (const o of cfgOpts) valueMap.set(o.value, o.label)
  }

  if (valueMap.size === 0) return raw

  if (raw.includes(',')) {
    return raw.split(',').map((v) => valueMap.get(v.trim()) ?? v.trim()).join(', ')
  }
  return valueMap.get(raw) ?? raw
}
