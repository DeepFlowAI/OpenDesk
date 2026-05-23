'use client'

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useParams, useSearchParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconEdit,
  IconTrash,
  IconSearch,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import {
  useOrganization,
  useDeleteOrganization,
  useOrgUsers,
  useOrganizationChanges,
  orgKeys,
} from '@/service/use-organizations'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import type { UnifiedField } from '@/models/field-definition'
import type { User } from '@/models/user'
import { FieldType } from '@/types/field-enums'
import {
  FieldValueDisplay,
  formatActorFieldValue,
} from '@/app/components/features/field-system/field-value-display'
import { EntityChangeTimeline } from '@/app/components/features/activity/entity-change-timeline'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'
import { OrgFormModal } from '../org-form-modal'

const DATETIME_KEYS = new Set(['created_at', 'updated_at'])
const SYSTEM_INFO_SYSTEM_KEYS = new Set(['public_id', 'created_by', 'updated_by'])
const SELECT_TYPES = new Set([
  'single_select',
  'multi_select',
  'single_select_tree',
  'multi_select_tree',
])

export default function OrganizationDetailPage() {
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const router = useRouter()
  const queryClient = useQueryClient()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'

  const orgRef = params.id
  const fromList = searchParams.get('from') === 'list'

  const { data: org, isLoading, error } = useOrganization(orgRef)
  const orgId = org?.id ?? 0
  const { data: fieldsData } = useUnifiedFields({
    domain: 'organization',
    include_metadata: true,
  })

  // User fields for sub-table
  const { data: userFieldsData } = useUnifiedFields({ domain: 'user' })

  const allFields: UnifiedField[] = useMemo(
    () => fieldsData?.items ?? [],
    [fieldsData],
  )
  const systemFields = useMemo(
    () => allFields.filter((f) => f.source === 'system'),
    [allFields],
  )
  const basicSystemFields = useMemo(
    () => systemFields.filter((f) => !SYSTEM_INFO_SYSTEM_KEYS.has(f.key ?? '')),
    [systemFields],
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
  const fieldDefMap = useMemo(() => {
    const m = new Map<string, UnifiedField>()
    for (const f of allFields) {
      if (f.id != null) m.set(String(f.id), f)
      if (f.key) m.set(f.key, f)
      if (f.slot_column) m.set(f.slot_column, f)
    }
    return m
  }, [allFields])

  // Sub-table: users under this organization
  const [rightTab, setRightTab] = useState<'users' | 'activity'>('users')
  const [userPage, setUserPage] = useState(1)
  const [userSearch, setUserSearch] = useState('')
  const [userSearchInput, setUserSearchInput] = useState('')
  const userPerPage = 10

  const {
    data: usersData,
    isLoading: usersLoading,
  } = useOrgUsers(org?.public_id ?? orgRef, {
    page: userPage,
    per_page: userPerPage,
    search: userSearch || undefined,
  }, !!org)
  const {
    data: changesData,
    isLoading: changesLoading,
    isError: changesError,
  } = useOrganizationChanges(orgId, { page: 1, per_page: 50 }, rightTab === 'activity')

  const userDisplayFields = useMemo<UnifiedField[]>(() => {
    const fields = userFieldsData?.items ?? []
    return fields
      .filter((f) => f.source === 'system' && ['name', 'email', 'phone'].includes(f.key ?? ''))
  }, [userFieldsData])

  const [editModalOpen, setEditModalOpen] = useState(false)
  const deleteMutation = useDeleteOrganization()

  const handleEditSuccess = useCallback(() => {
    setEditModalOpen(false)
    queryClient.invalidateQueries({ queryKey: orgKeys.detail(orgRef) })
    queryClient.invalidateQueries({ queryKey: orgKeys.detail(orgId) })
    queryClient.invalidateQueries({ queryKey: orgKeys.queries() })
  }, [queryClient, orgId, orgRef])

  const handleDelete = useCallback(async () => {
    if (!orgId) return
    const msg = isZh
      ? '确定要删除此组织吗？此操作不可撤销。'
      : 'Are you sure you want to delete this organization? This action cannot be undone.'
    if (!window.confirm(msg)) return
    try {
      await deleteMutation.mutateAsync(orgId)
      router.push('/workspace/organizations')
    } catch {
      // handled by mutation
    }
  }, [isZh, orgId, deleteMutation, router])

  useEffect(() => {
    if (!org?.public_id || !orgRef || !/^\d+$/.test(orgRef)) return
    const qs = searchParams.toString()
    router.replace(`/workspace/organizations/${org.public_id}${qs ? `?${qs}` : ''}`)
  }, [router, searchParams, org?.public_id, orgRef])

  const handleUserSearch = useCallback(() => {
    setUserSearch(userSearchInput)
    setUserPage(1)
  }, [userSearchInput])

  const getFieldRaw = useCallback(
    (field: UnifiedField): unknown => {
      if (!org) return undefined
      const key = field.key
      if (key && field.source !== 'custom') {
        return (org as Record<string, unknown>)[key]
      }
      if (key && org.custom_fields) {
        return org.custom_fields[key] ?? (field.id != null ? org.custom_fields[String(field.id)] : undefined)
      }
      if (field.id != null && org.custom_fields) {
        return org.custom_fields[String(field.id)]
      }
      return undefined
    },
    [org],
  )

  const getFieldValue = useCallback(
    (field: UnifiedField): string => {
      if (!org) return ''
      const key = field.key
      if (key && field.source !== 'custom') {
        const raw = (org as Record<string, unknown>)[key]
        if (raw == null) return '—'
        if (field.type_config?.value_kind === 'actor') return formatActorFieldValue(raw)
        if (DATETIME_KEYS.has(key)) return new Date(raw as string).toLocaleString()
        if (SELECT_TYPES.has(field.field_type)) {
          return resolveSelectValue(String(raw), field)
        }
        return String(raw)
      }
      if (org.custom_fields) {
        const val = key && org.custom_fields[key] != null
          ? org.custom_fields[key]
          : field.id != null
            ? org.custom_fields[String(field.id)]
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
    [org],
  )

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{isZh ? '加载中...' : 'Loading...'}</p>
      </div>
    )
  }

  if (error || !org) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-muted-foreground">
          {isZh ? '组织不存在或无权限访问' : 'Organization not found or access denied'}
        </p>
        <button
          onClick={() => router.push('/workspace/organizations')}
          className="text-sm font-medium text-primary hover:underline"
        >
          {isZh ? '返回组织列表' : 'Back to organization list'}
        </button>
      </div>
    )
  }

  const userTotal = usersData?.total ?? 0
  const userTotalPages = usersData?.pages ?? 0

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      {/* Top bar */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-white px-6 py-3">
        {fromList && (
          <button
            onClick={() => router.push('/workspace/organizations')}
            className="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <IconArrowLeft size={16} />
            {isZh ? '返回列表' : 'Back to list'}
          </button>
        )}
        <h2 className="flex-1 text-base font-semibold text-foreground">{org.name}</h2>
        <button
          onClick={() => setEditModalOpen(true)}
          className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
        >
          <IconEdit size={16} />
          {isZh ? '编辑组织' : 'Edit'}
        </button>
        <button
          onClick={handleDelete}
          disabled={deleteMutation.isPending}
          className="flex h-9 items-center gap-1.5 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
        >
          <IconTrash size={16} />
          {isZh ? '删除' : 'Delete'}
        </button>
      </div>

      {/* Main content: left profile + right user list */}
      <div className="flex min-h-0 flex-1 overflow-hidden bg-white">
        {/* Left: Profile panel (info card keeps tinted surface) */}
        <div className="w-[32rem] shrink-0 overflow-y-auto bg-white p-6">
          <div className="rounded-xl border border-border bg-accent/50 p-5">
            {/* Basic info */}
            <h3 className="mb-3 text-sm font-semibold text-foreground">
              {isZh ? '基本信息' : 'Basic Info'}
            </h3>
            <div className="flex flex-col gap-2.5">
              {basicSystemFields.map((f) => (
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

            {/* Custom fields */}
            {customFields.length > 0 && (
              <>
                <h3 className="mb-3 mt-6 text-sm font-semibold text-foreground">
                  {isZh ? '自定义字段' : 'Custom Fields'}
                </h3>
                <div className="flex flex-col gap-2.5">
                  {customFields.map((f) => {
                    const raw =
                      org.custom_fields
                        ? f.key && org.custom_fields[f.key] != null
                          ? org.custom_fields[f.key]
                          : f.id != null
                            ? org.custom_fields[String(f.id)]
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

            {/* System info */}
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
              <div className="flex items-start gap-3">
                <span className="w-20 shrink-0 text-sm text-muted-foreground">
                  {isZh ? '用户数量' : 'User Count'}
                </span>
                <span className="min-w-0 flex-1 break-words text-sm text-foreground">
                  {org.user_count}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Users and activity under this organization */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-l border-border bg-white">
          <div className="flex shrink-0 items-center gap-3 border-b border-border bg-white px-6 py-3">
            <div className="flex items-center">
              <button
                type="button"
                onClick={() => setRightTab('users')}
                className={cn(
                  'relative px-4 py-1.5 text-sm font-medium transition-colors',
                  rightTab === 'users' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground/80',
                )}
              >
                {isZh ? '名下用户' : 'Users'}
                {rightTab === 'users' && (
                  <span className="absolute bottom-0 left-4 right-4 h-0.5 rounded-full bg-primary" />
                )}
              </button>
              <button
                type="button"
                onClick={() => setRightTab('activity')}
                className={cn(
                  'relative px-4 py-1.5 text-sm font-medium transition-colors',
                  rightTab === 'activity' ? 'text-foreground' : 'text-muted-foreground hover:text-foreground/80',
                )}
              >
                {isZh ? '动态' : 'Activity'}
                {rightTab === 'activity' && (
                  <span className="absolute bottom-0 left-4 right-4 h-0.5 rounded-full bg-primary" />
                )}
              </button>
            </div>
            {rightTab === 'users' && (
              <div className="relative max-w-xs flex-1">
                <IconSearch size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  value={userSearchInput}
                  onChange={(e) => setUserSearchInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleUserSearch()}
                  placeholder={isZh ? '搜索用户...' : 'Search users...'}
                  className="h-8 w-full rounded-lg border border-border bg-white pl-8 pr-3 text-xs text-foreground outline-none focus:border-ring"
                />
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto bg-white">
            {rightTab === 'activity' ? (
              <div className="p-6">
                <EntityChangeTimeline
                  changes={changesData?.items ?? []}
                  isLoading={changesLoading}
                  isError={changesError}
                  isZh={isZh}
                  resolveFieldDef={(fieldKey) => fieldDefMap.get(fieldKey)}
                  emptyText={isZh ? '暂无动态' : 'No activity yet'}
                />
              </div>
            ) : usersLoading ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-muted-foreground">Loading...</p>
              </div>
            ) : !usersData?.items?.length ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-muted-foreground">
                  {isZh ? '暂无用户' : 'No users'}
                </p>
              </div>
            ) : (
              <table className="w-full">
                <thead className="sticky top-0 z-10 border-b border-border bg-white">
                  <tr>
                    <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                      {isZh ? '名称' : 'Name'}
                    </th>
                    <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                      {isZh ? '邮箱' : 'Email'}
                    </th>
                    <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                      {isZh ? '手机' : 'Phone'}
                    </th>
                    <th className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase text-muted-foreground">
                      {isZh ? '操作' : 'Actions'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {usersData.items.map((user: User) => (
                    <tr
                      key={user.id}
                      className="border-b border-border transition-colors hover:bg-accent/50"
                    >
                      <td className="px-4 py-3 text-sm text-foreground">{user.name}</td>
                      <td className="px-4 py-3 text-sm text-foreground/80">{user.email ?? '—'}</td>
                      <td className="px-4 py-3 text-sm text-foreground/80">{user.phone ?? '—'}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => router.push(`/workspace/users/${user.public_id || user.id}`)}
                          className="text-sm font-medium text-primary transition-colors hover:underline"
                        >
                          {isZh ? '查看详情' : 'View Detail'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Users pagination */}
          {userTotal > 0 && (
            <div className="flex shrink-0 items-center justify-between border-t border-border bg-white px-6 py-3">
              <span className="text-xs text-muted-foreground">
                {isZh ? `共 ${userTotal} 条` : `${userTotal} total`}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  disabled={userPage <= 1}
                  onClick={() => setUserPage(userPage - 1)}
                  className="h-7 rounded-md border border-border px-2 text-xs text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
                >
                  {isZh ? '上一页' : 'Prev'}
                </button>
                <span className="text-xs text-muted-foreground">
                  {userPage} / {userTotalPages}
                </span>
                <button
                  disabled={userPage >= userTotalPages}
                  onClick={() => setUserPage(userPage + 1)}
                  className="h-7 rounded-md border border-border px-2 text-xs text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
                >
                  {isZh ? '下一页' : 'Next'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Edit modal */}
      {editModalOpen && (
        <OrgFormModal
          mode="edit"
          organization={org}
          onClose={() => setEditModalOpen(false)}
          onSuccess={handleEditSuccess}
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
