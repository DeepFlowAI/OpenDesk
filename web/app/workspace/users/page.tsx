'use client'

import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import {
  IconPlus,
  IconFilter,
  IconColumns3,
  IconSearch,
  IconChevronDown,
  IconChevronRight,
  IconX,
  IconUsers,
  IconBuilding,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  useQueryUsers,
  useEnabledUserViews,
  useUserViewCounts,
  useUserViewGroups,
} from '@/service/use-users'
import { useEnabledOrgViews, useOrgViewCounts } from '@/service/use-organizations'
import { useSystemSettings } from '@/service/use-system-settings'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type { UserView, ConditionItem, ColumnConfigItem } from '@/models/user-view'
import type { User, UserQueryPayload } from '@/models/user'
import type { UnifiedField } from '@/models/field-definition'
import type { ViewGroupRequestPayload } from '@/models/view-group'
import { FilterDrawer } from './filter-drawer'
import { ColumnsDrawer } from './columns-drawer'
import { UserFormModal } from './user-form-modal'
import { GroupBar } from '@/components/workspace/group-bar'
import {
  formatActorFieldValue,
  formatFileFieldValue,
} from '@/app/components/features/field-system/field-value-display'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'

// ── localStorage helpers for column config persistence ──

const COL_STORAGE_PREFIX = 'ws_user_cols_'

function getColStorageKey(viewId: number | null): string {
  return `${COL_STORAGE_PREFIX}${viewId ?? 'default'}`
}

function readColsFromStorage(viewId: number | null): ColumnConfigItem[] | null {
  try {
    const raw = localStorage.getItem(getColStorageKey(viewId))
    if (!raw) return null
    return JSON.parse(raw) as ColumnConfigItem[]
  } catch {
    return null
  }
}

function writeColsToStorage(viewId: number | null, cols: ColumnConfigItem[]): void {
  try {
    localStorage.setItem(getColStorageKey(viewId), JSON.stringify(cols))
  } catch { /* quota exceeded – ignore */ }
}

function removeColsFromStorage(viewId: number | null): void {
  try {
    localStorage.removeItem(getColStorageKey(viewId))
  } catch { /* ignore */ }
}

// ── Main page ──

export default function WorkspaceUsersPage() {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const searchParams = useSearchParams()

  const { data: systemSettings } = useSystemSettings()
  const organizationEnabled = systemSettings?.organization_enabled === true
  const { data: views, isLoading: viewsLoading } = useEnabledUserViews()
  const { data: viewCountsData } = useUserViewCounts()
  const { data: orgViews } = useEnabledOrgViews(organizationEnabled)
  const { data: orgViewCountsData } = useOrgViewCounts(organizationEnabled)

  const { data: fieldsData } = useUnifiedFields({ domain: 'user', include_metadata: true })

  const totalUserCount = viewCountsData?.total_count ?? 0
  const totalOrgCount = orgViewCountsData?.total_count ?? 0
  const orgViewCountMap = useMemo(() => {
    const m = new Map<number, number>()
    for (const item of orgViewCountsData?.items ?? []) m.set(item.view_id, item.count)
    return m
  }, [orgViewCountsData])
  const viewCountMap = useMemo(() => {
    const m = new Map<number, number>()
    for (const item of viewCountsData?.items ?? []) m.set(item.view_id, item.count)
    return m
  }, [viewCountsData])

  const allFieldsRaw: UnifiedField[] = useMemo(() => fieldsData?.items ?? [], [fieldsData])
  // Split: configurable fields (system + custom) vs pinned metadata fields
  const allFields: UnifiedField[] = useMemo(
    () => allFieldsRaw.filter((f) => f.source !== 'metadata'), [allFieldsRaw],
  )
  const metadataFields: UnifiedField[] = useMemo(
    () => allFieldsRaw.filter((f) => f.source === 'metadata'), [allFieldsRaw],
  )

  // Active view — 'all' means no view filter; number means specific view
  const viewIdParam = searchParams.get('view')
  const [selectedViewId, setSelectedViewId] = useState<number | 'all'>(
    viewIdParam && viewIdParam !== 'all' ? Number(viewIdParam) : 'all'
  )

  const groupParam = searchParams.get('group')
  const [groupValue, setGroupValue] = useState<string | undefined>(
    groupParam ?? undefined,
  )

  const activeView: UserView | null = useMemo(() => {
    if (!views || selectedViewId === 'all') return null
    return views.find((v) => v.id === selectedViewId) ?? null
  }, [views, selectedViewId])

  // Pagination
  const [page, setPage] = useState(1)
  const perPage = 20

  // Search
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Temp filter state (session-only, not persisted)
  const [tempConditions, setTempConditions] = useState<ConditionItem[]>([])
  const [tempConditionLogic, setTempConditionLogic] = useState<'and' | 'or'>('and')
  const hasActiveFilter = tempConditions.length > 0

  // Column state — persisted per-view in localStorage
  const [columnOverrides, setColumnOverrides] = useState<ColumnConfigItem[] | null>(null)
  const colInitRef = useRef(false)
  useEffect(() => {
    if (!colInitRef.current) {
      colInitRef.current = true
      setColumnOverrides(readColsFromStorage(activeView?.id ?? null))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const hasColumnOverride = columnOverrides !== null

  // Drawers & modals
  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false)
  const [columnsDrawerOpen, setColumnsDrawerOpen] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)

  // Sidebar groups
  const [userGroupOpen, setUserGroupOpen] = useState(true)
  const [orgGroupOpen, setOrgGroupOpen] = useState(true)

  const groupsEnabled =
    selectedViewId !== 'all' &&
    activeView != null &&
    activeView.group_field_id != null

  const groupsRequest: ViewGroupRequestPayload = useMemo(
    () => ({
      search: search || undefined,
      temp_conditions: tempConditions.length > 0 ? tempConditions : undefined,
      temp_condition_logic:
        tempConditions.length > 0 ? tempConditionLogic : undefined,
    }),
    [search, tempConditions, tempConditionLogic],
  )

  const { data: groupsData, isLoading: groupsLoading } = useUserViewGroups(
    selectedViewId === 'all' ? null : (selectedViewId as number),
    groupsRequest,
    groupsEnabled,
  )

  const groupField: UnifiedField | null = useMemo(() => {
    if (!groupsEnabled || !activeView?.group_field_id) return null
    return (
      allFieldsRaw.find((f) => f.id === activeView.group_field_id) ?? null
    )
  }, [groupsEnabled, activeView, allFieldsRaw])

  // Drop a stale `?group=` param if the current view no longer has a group field
  // configured (or the field was removed). Keeps the URL honest after admin edits.
  useEffect(() => {
    if (!groupsEnabled && groupValue !== undefined) {
      setGroupValue(undefined)
    }
  }, [groupsEnabled, groupValue])

  // Build query payload
  const queryPayload: UserQueryPayload = useMemo(
    () => ({
      view_id: selectedViewId === 'all' ? null : selectedViewId,
      search: search || undefined,
      temp_conditions: tempConditions.length > 0 ? tempConditions : undefined,
      temp_condition_logic: tempConditions.length > 0 ? tempConditionLogic : undefined,
      group_value: groupsEnabled ? groupValue : undefined,
      page,
      per_page: perPage,
    }),
    [
      selectedViewId,
      search,
      tempConditions,
      tempConditionLogic,
      groupsEnabled,
      groupValue,
      page,
      perPage,
    ]
  )

  const { data: usersData, isLoading: usersLoading } = useQueryUsers(queryPayload)

  // Resolve visible columns
  const visibleColumns = useMemo(() => {
    if (columnOverrides) {
      return columnOverrides.filter((c) => c.visible).sort((a, b) => a.sort_order - b.sort_order)
    }
    if (activeView?.custom_columns_enabled && activeView.columns_config?.length > 0) {
      return activeView.columns_config.filter((c) => c.visible).sort((a, b) => a.sort_order - b.sort_order)
    }
    return null
  }, [columnOverrides, activeView])

  type DisplayColumn = {
    field_key: string | null
    field_id: number | null
    name: string
    field_type: string
    source: 'system' | 'custom' | 'metadata'
  }

  // Metadata columns — always pinned at the end, never affected by overrides
  const pinnedMetadataCols: DisplayColumn[] = useMemo(
    () => metadataFields.map((f) => ({
      field_key: f.key,
      field_id: f.id,
      name: f.name,
      field_type: f.field_type,
      source: 'metadata' as const,
    })),
    [metadataFields],
  )

  const displayColumns: DisplayColumn[] = useMemo(() => {
    let configurable: DisplayColumn[]

    if (visibleColumns) {
      configurable = visibleColumns.map((col) => {
        const field = allFields.find((f) =>
          col.field_key ? f.key === col.field_key : f.id === col.field_id
        )
        return {
          field_key: col.field_key ?? field?.key ?? null,
          field_id: col.field_id ?? field?.id ?? null,
          name: field?.name ?? col.field_key ?? `#${col.field_id}`,
          field_type: field?.field_type ?? '',
          source: (field?.source ?? 'custom') as DisplayColumn['source'],
        }
      })
    } else {
      configurable = allFields.map((f) => ({
        field_key: f.key,
        field_id: f.id,
        name: f.name,
        field_type: f.field_type,
        source: f.source as DisplayColumn['source'],
      }))
    }

    return [...configurable, ...pinnedMetadataCols]
  }, [visibleColumns, allFields, pinnedMetadataCols])

  // Build a value→label lookup map for select-type fields
  const fieldLookup = useMemo(() => buildFieldLookup(allFieldsRaw, locale), [allFieldsRaw, locale])

  // Handlers
  const handleSelectView = useCallback((viewId: number | 'all') => {
    setSelectedViewId(viewId)
    setPage(1)
    setSearch('')
    setSearchInput('')
    setTempConditions([])
    setTempConditionLogic('and')
    setGroupValue(undefined)
    setColumnOverrides(readColsFromStorage(viewId === 'all' ? null : viewId))
    router.replace(buildUsersUrl(viewId, undefined), { scroll: false })
  }, [router])

  const handleSelectGroup = useCallback((value: string | undefined) => {
    setGroupValue(value)
    setPage(1)
    router.replace(buildUsersUrl(selectedViewId, value), { scroll: false })
  }, [router, selectedViewId])

  const handleSearch = useCallback(() => {
    setSearch(searchInput)
    setPage(1)
  }, [searchInput])

  const handleClearSearch = useCallback(() => {
    setSearch('')
    setSearchInput('')
    setPage(1)
  }, [])

  const showSearchClear = search.trim().length > 0 || searchInput.trim().length > 0

  const handleClearFilter = useCallback(() => {
    setTempConditions([])
    setTempConditionLogic('and')
    setPage(1)
  }, [])

  const handleApplyFilter = useCallback((conditions: ConditionItem[], logic: 'and' | 'or') => {
    setTempConditions(conditions)
    setTempConditionLogic(logic)
    setPage(1)
  }, [])

  const storageViewId = selectedViewId === 'all' ? null : selectedViewId

  const handleResetColumns = useCallback(() => {
    setColumnOverrides(null)
    removeColsFromStorage(storageViewId)
  }, [storageViewId])

  const handleApplyColumns = useCallback((cols: ColumnConfigItem[]) => {
    setColumnOverrides(cols)
    writeColsToStorage(storageViewId, cols)
  }, [storageViewId])

  const totalPages = usersData?.pages ?? 0
  const total = usersData?.total ?? 0

  return (
    <div className="flex h-full">
      {/* Left: Contacts sidebar */}
      <aside className="flex w-[280px] shrink-0 flex-col bg-accent" style={{ borderRight: '1px solid #e5e5e5' }}>
        {/* Header */}
        <div className="px-3 pb-2.5 pt-3.5">
          <h2 className="text-[15px] font-semibold text-foreground">
            {locale === 'zh' ? '通讯录' : 'Contacts'}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* ── Users group ── */}
          <div>
            <button
              onClick={() => setUserGroupOpen(!userGroupOpen)}
              className="flex w-full items-center justify-between px-3 py-2.5"
            >
              <span className="flex items-center gap-2">
                <IconUsers size={18} className="text-foreground" />
                <span className="text-sm font-semibold text-foreground">
                  {locale === 'zh' ? '用户' : 'Users'}
                </span>
              </span>
              {userGroupOpen
                ? <IconChevronDown size={16} className="text-muted-foreground" />
                : <IconChevronRight size={16} className="text-muted-foreground" />}
            </button>

            {userGroupOpen && (
              <div className="pb-2">
                {viewsLoading ? (
                  <div className="px-4 py-2 text-xs text-muted-foreground">Loading...</div>
                ) : (
                  <>
                    {/* "全部" — always first */}
                    <SidebarViewItem
                      label={locale === 'zh' ? '全部' : 'All'}
                      count={totalUserCount}
                      active={selectedViewId === 'all'}
                      onClick={() => handleSelectView('all')}
                    />
                    {/* System views */}
                    {views?.map((v) => (
                      <SidebarViewItem
                        key={v.id}
                        label={v.name}
                        count={viewCountMap.get(v.id)}
                        active={selectedViewId === v.id}
                        onClick={() => handleSelectView(v.id)}
                      />
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          {organizationEnabled && (
            <div>
              <button
                onClick={() => setOrgGroupOpen(!orgGroupOpen)}
                className="flex w-full items-center justify-between px-3 py-2.5 mt-2"
              >
                <span className="flex items-center gap-2">
                  <IconBuilding size={18} className="text-foreground" />
                  <span className="text-sm font-semibold text-foreground">
                    {locale === 'zh' ? '组织' : 'Organizations'}
                  </span>
                </span>
                {orgGroupOpen
                  ? <IconChevronDown size={16} className="text-muted-foreground" />
                  : <IconChevronRight size={16} className="text-muted-foreground" />}
              </button>

              {orgGroupOpen && (
                <div className="pb-2">
                  <SidebarViewItem
                    label={locale === 'zh' ? '全部' : 'All'}
                    count={totalOrgCount}
                    active={false}
                    onClick={() => router.push('/workspace/organizations')}
                  />
                  {orgViews?.map((v) => (
                    <SidebarViewItem
                      key={v.id}
                      label={v.name}
                      count={orgViewCountMap.get(v.id)}
                      active={false}
                      onClick={() => router.push(`/workspace/organizations?view=${v.id}`)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* Right: Main content — layout matches 客服工作台用户.pen: title row + primary action, then search toolbar */}
      <div className="flex flex-1 flex-col overflow-hidden bg-white">
        {/* View title + create (design: same row, no divider below before search) */}
        <div className="flex items-center justify-between px-5 pb-2.5 pt-3.5">
          <h3 className="text-base font-semibold text-foreground">
            {selectedViewId === 'all'
              ? (locale === 'zh' ? '全部' : 'All')
              : activeView?.name ?? ''}
          </h3>
          <button
            type="button"
            onClick={() => setCreateModalOpen(true)}
            className="flex h-9 items-center gap-1.5 rounded-lg bg-[#252525] px-4 text-sm font-medium text-white transition-colors hover:bg-[#252525]/90"
          >
            <IconPlus size={16} />
            {locale === 'zh' ? '新建用户' : 'Create User'}
          </button>
        </div>

        {/* Toolbar: search + filter + columns only */}
        <div className="flex items-center gap-3 px-5 pb-3.5 pt-3">
          {/* Search */}
          <div className="relative w-full max-w-[240px]">
            <IconSearch size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder={locale === 'zh' ? '搜索用户...' : 'Search users...'}
              className={cn(
                'h-9 w-full rounded-lg border-0 bg-[#F4F4F5] pl-9 text-sm text-foreground outline-none ring-1 ring-transparent placeholder:text-[#71717A] focus:ring-2 focus:ring-ring',
                showSearchClear ? 'pr-9' : 'pr-3',
              )}
            />
            {showSearchClear && (
              <button
                type="button"
                onClick={handleClearSearch}
                className="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full bg-[#A1A1AA] text-white transition-colors hover:bg-[#71717A]"
                title={locale === 'zh' ? '清除搜索' : 'Clear search'}
              >
                <IconX size={12} stroke={2.5} />
              </button>
            )}
          </div>

          <div className="flex-1 min-w-0" />

          {/* Filter button */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setFilterDrawerOpen(true)}
              className={cn(
                'flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm transition-colors',
                hasActiveFilter
                  ? 'border-ring bg-info/10 text-primary'
                  : 'border-border text-foreground/80 hover:bg-accent'
              )}
            >
              <IconFilter size={16} />
              {locale === 'zh' ? '筛选' : 'Filter'}
            </button>
            {hasActiveFilter && (
              <button
                onClick={handleClearFilter}
                className="flex h-9 items-center rounded-lg px-1.5 text-primary transition-colors hover:bg-info/10"
                title={locale === 'zh' ? '清除筛选' : 'Clear filter'}
              >
                <IconX size={16} />
              </button>
            )}
          </div>

          {/* Columns button */}
          <button
            onClick={() => setColumnsDrawerOpen(true)}
            className={cn(
              'flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm transition-colors',
              hasColumnOverride
                ? 'border-ring bg-info/10 text-primary'
                : 'border-border text-foreground/80 hover:bg-accent'
            )}
          >
            <IconColumns3 size={16} />
            {locale === 'zh' ? '列字段' : 'Columns'}
          </button>
        </div>

        {groupsEnabled && (
          <GroupBar
            locale={locale}
            items={groupsData?.items ?? []}
            total={groupsData?.total ?? 0}
            activeValue={groupValue}
            field={groupField}
            onChange={handleSelectGroup}
            isLoading={groupsLoading}
          />
        )}

        <div className="mx-5 h-px shrink-0 bg-border" aria-hidden />

        {/* Table — horizontal inset matches pen tableWrap [0,20,12,20] */}
        <div className="flex-1 overflow-auto px-5 pb-3 [scrollbar-gutter:stable]">
          {usersLoading ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-muted-foreground">Loading...</p>
            </div>
          ) : !usersData?.items?.length ? (
            <div className="flex h-full flex-col items-center justify-center gap-3">
              <p className="text-sm text-muted-foreground">
                {hasActiveFilter
                  ? (locale === 'zh' ? '无匹配条件的用户' : 'No users match the filter')
                  : (locale === 'zh' ? '暂无用户数据' : 'No user data')}
              </p>
              {hasActiveFilter && (
                <button
                  onClick={handleClearFilter}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  {locale === 'zh' ? '清除筛选' : 'Clear Filter'}
                </button>
              )}
            </div>
          ) : (
            <table
              className="w-full"
              style={{ minWidth: `max(100%, ${displayColumns.length * 140}px)` }}
            >
              <thead className="sticky top-0 z-10 bg-white">
                <tr className="border-b border-border">
                  {displayColumns.map((col, idx) => (
                    <th
                      key={col.field_key ?? `col-${idx}`}
                      className="whitespace-nowrap px-6 py-3 text-left text-xs font-semibold uppercase text-muted-foreground"
                      style={{ minWidth: getColumnMinWidth(col.field_type, col.field_key) }}
                    >
                      {col.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {usersData.items.map((user) => (
                  <tr
                    key={user.id}
                    className="border-b border-border transition-colors hover:bg-accent/50 cursor-pointer"
                    onClick={() => router.push(`/workspace/users/${user.id}?from=list`)}
                  >
                    {displayColumns.map((col, idx) => {
                      const val = getCellValue(user, col, fieldLookup, locale)
                      return (
                        <td
                          key={col.field_key ?? col.field_id ?? `cell-${idx}`}
                          className="max-w-[280px] overflow-hidden px-6 py-3 text-sm text-foreground/80"
                          style={{ minWidth: getColumnMinWidth(col.field_type, col.field_key) }}
                        >
                          <span className="block truncate">{val}</span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {total > 0 && (
          <>
            <div className="mx-5 h-px shrink-0 bg-border" aria-hidden />
            <div className="flex items-center justify-between px-5 py-3">
            <span className="text-xs text-muted-foreground">
              {locale === 'zh' ? `共 ${total} 条` : `${total} total`}
            </span>
            <div className="flex items-center gap-1.5">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="h-8 rounded-md border border-border px-3 text-xs text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {locale === 'zh' ? '上一页' : 'Prev'}
              </button>
              <span className="text-xs text-muted-foreground">
                {page} / {totalPages}
              </span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                className="h-8 rounded-md border border-border px-3 text-xs text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
              >
                {locale === 'zh' ? '下一页' : 'Next'}
              </button>
            </div>
          </div>
          </>
        )}
      </div>

      {/* Filter Drawer */}
      {filterDrawerOpen && (
        <FilterDrawer
          locale={locale}
          fields={allFields}
          conditions={tempConditions}
          conditionLogic={tempConditionLogic}
          onApply={handleApplyFilter}
          onClose={() => setFilterDrawerOpen(false)}
        />
      )}

      {/* Columns Drawer */}
      {columnsDrawerOpen && (
        <ColumnsDrawer
          locale={locale}
          fields={allFields}
          baselineConfig={activeView?.custom_columns_enabled ? activeView.columns_config : null}
          currentOverride={columnOverrides}
          onApply={handleApplyColumns}
          onReset={handleResetColumns}
          onClose={() => setColumnsDrawerOpen(false)}
        />
      )}

      {/* Create User Modal */}
      {createModalOpen && (
        <UserFormModal
          mode="create"
          onClose={() => setCreateModalOpen(false)}
          onSuccess={() => setCreateModalOpen(false)}
        />
      )}
    </div>
  )
}

function buildUsersUrl(
  viewId: number | 'all',
  group: string | undefined,
): string {
  const usp = new URLSearchParams()
  if (viewId !== 'all') usp.set('view', String(viewId))
  if (group !== undefined) usp.set('group', group)
  const qs = usp.toString()
  return qs ? `/workspace/users?${qs}` : '/workspace/users'
}

const SYSTEM_KEYS = new Set([
  'name', 'nickname', 'external_id', 'avatar_color', 'channel_id', 'organization_id',
  'email', 'phone', 'web_id', 'gender', 'address', 'remark',
  'created_by', 'updated_by', 'created_at', 'updated_at',
])

const SYSTEM_KEY_ALIAS: Record<string, string> = {
  nickname: 'name',
}

const DATETIME_KEYS = new Set(['created_at', 'updated_at'])

const GENDER_LABELS: Record<string, { zh: string; en: string }> = {
  male: { zh: '男', en: 'Male' },
  female: { zh: '女', en: 'Female' },
  unknown: { zh: '未知', en: 'Unknown' },
  other: { zh: '其他', en: 'Other' },
}

type FieldValueLookup = Map<string, Map<string, string>>

function buildFieldLookup(fields: UnifiedField[], locale: string): FieldValueLookup {
  const lookup: FieldValueLookup = new Map()
  for (const f of fields) {
    const ft = f.field_type
    if (!['single_select', 'multi_select', 'single_select_tree', 'multi_select_tree'].includes(ft)) continue

    const key = f.key ?? (f.id != null ? String(f.id) : '')
    const valueMap = new Map<string, string>()

    if (f.options?.length) {
      for (const o of f.options) {
        if (o.is_active) valueMap.set(o.value, o.label)
      }
    }
    if (f.tree_nodes?.length) {
      for (const n of f.tree_nodes) {
        if (n.is_active) valueMap.set(n.value, n.label)
      }
    }
    const cfgOpts = (f.type_config as { options?: { label: string; value: string }[] })?.options
    if (cfgOpts) {
      for (const o of cfgOpts) valueMap.set(o.value, o.label)
    }

    if (valueMap.size > 0) {
      lookup.set(key, valueMap)
      if (f.id != null) lookup.set(String(f.id), valueMap)
    }
  }
  return lookup
}

function resolveSelectLabel(raw: string, lookupKey: string, fieldLookup: FieldValueLookup): string {
  const valueMap = fieldLookup.get(lookupKey)
  if (!valueMap) return raw
  // Handle comma-separated multi-select values
  if (raw.includes(',')) {
    return raw.split(',').map((v) => valueMap.get(v.trim()) ?? v.trim()).join(', ')
  }
  return valueMap.get(raw) ?? raw
}

function getCellValue(
  user: User,
  col: { field_key: string | null; field_id: number | null; field_type: string; source: string },
  fieldLookup: FieldValueLookup,
  locale: string,
): string {
  const { field_key, field_id, field_type } = col

  if (field_key && SYSTEM_KEYS.has(field_key)) {
    const realKey = SYSTEM_KEY_ALIAS[field_key] ?? field_key
    const raw = (user as Record<string, unknown>)[realKey]
    if (raw == null) return ''
    if (field_key === 'created_by' || field_key === 'updated_by') return formatActorFieldValue(raw)
    if (DATETIME_KEYS.has(field_key)) return new Date(raw as string).toLocaleString()

    // Gender: map value to localized label
    if (field_key === 'gender') {
      const g = GENDER_LABELS[String(raw)]
      return g ? (locale === 'zh' ? g.zh : g.en) : String(raw)
    }

    // System select fields with type_config options
    if (['single_select', 'multi_select'].includes(field_type) && field_key) {
      return resolveSelectLabel(String(raw), field_key, fieldLookup)
    }

    return String(raw)
  }

  if (user.custom_fields) {
    const customKey = field_key && !SYSTEM_KEYS.has(field_key) ? field_key : null
    const legacyIdKey = field_id != null ? String(field_id) : null
    const lookupKey = customKey ?? legacyIdKey ?? ''
    const val = customKey && user.custom_fields[customKey] != null
      ? user.custom_fields[customKey]
      : legacyIdKey
        ? user.custom_fields[legacyIdKey]
        : null
    if (val == null) return ''
    if (field_type === 'file') {
      return formatFileFieldValue(val, locale === 'zh')
    }
    const str = Array.isArray(val) ? val.join(',') : String(val)
    if (field_type === 'datetime') {
      return formatDatetimeForDisplay(str)
    }
    if (['single_select', 'multi_select', 'single_select_tree', 'multi_select_tree'].includes(field_type)) {
      return resolveSelectLabel(str, lookupKey, fieldLookup)
    }
    return str
  }

  return ''
}

function getColumnMinWidth(fieldType: string, fieldKey: string | null): number {
  if (fieldKey === 'created_at' || fieldKey === 'updated_at') return 160
  if (fieldKey === 'created_by' || fieldKey === 'updated_by') return 160
  if (fieldKey === 'email') return 180
  if (fieldKey === 'phone') return 130
  if (fieldKey === 'address' || fieldKey === 'remark') return 160
  switch (fieldType) {
    case 'email': return 180
    case 'url': return 180
    case 'phone': return 130
    case 'datetime': return 160
    case 'date': return 110
    case 'number': return 100
    case 'multi_line_text':
    case 'rich_text': return 160
    default: return 120
  }
}

function SidebarViewItem({
  label,
  count,
  active,
  onClick,
}: {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex h-9 w-full items-center transition-colors',
        active ? 'bg-border' : 'hover:bg-border/60',
      )}
    >
      {active && <span className="h-full w-[3px] shrink-0 bg-primary" />}
      <span
        className={cn(
          'flex min-w-0 flex-1 items-center justify-between pr-[15px]',
          active ? 'pl-3' : 'pl-[15px]',
        )}
      >
        <span
          className={cn(
            'min-w-0 flex-1 truncate text-left text-[13px] text-foreground',
            active ? 'font-medium' : 'font-normal',
          )}
        >
          {label}
        </span>
        {count !== undefined && (
          <span className="ml-2 shrink-0 text-[13px] text-[#999]">{count}</span>
        )}
      </span>
    </button>
  )
}
