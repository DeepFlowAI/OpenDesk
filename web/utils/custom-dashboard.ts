import type { DashboardComponent, DashboardFilter, DashboardSnapshotPayload } from '@/models/custom-dashboard'
import type { UnifiedField } from '@/models/field-definition'
import type { ConditionItem } from '@/models/ticket-view'

export const DASHBOARD_MAX_COMPONENTS = 20
export const DASHBOARD_MAX_FILTERS = 8
export const DASHBOARD_MAX_CODE_BYTES = 64 * 1024

export const DEFAULT_DASHBOARD_CODE = `from opendesk import query

def run():
    value = query.tickets.count()
    return {
        "type": "metric",
        "value": value,
        "label": "Tickets",
    }
`

export type DashboardValidationErrors = Partial<Record<'name' | 'slug' | 'description' | 'components', string>>

export function validateDashboardForm(
  value: Pick<DashboardSnapshotPayload, 'name' | 'description' | 'components'> & { slug?: string },
  requireSlug = false,
): DashboardValidationErrors {
  const errors: DashboardValidationErrors = {}
  const name = value.name.trim()
  if (!name) errors.name = 'required'
  else if (name.length > 80) errors.name = 'too_long'
  if (requireSlug && !/^[a-z][a-z0-9_]{1,63}$/.test(value.slug ?? '')) errors.slug = 'invalid'
  if ((value.description?.trim().length ?? 0) > 300) errors.description = 'too_long'
  if (value.components.length > DASHBOARD_MAX_COMPONENTS) errors.components = 'too_many'
  return errors
}

export function validateComponent(component: DashboardComponent): 'title_required' | 'run_required' | 'code_too_large' | null {
  if (!component.title.trim()) return 'title_required'
  if (new TextEncoder().encode(component.code).length > DASHBOARD_MAX_CODE_BYTES) return 'code_too_large'
  if (!/(?:^|\n)\s*def\s+run\s*\(\s*\)\s*:/.test(component.code)) return 'run_required'
  return null
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, Math.round(value)))
}

export function clampComponent(component: DashboardComponent): DashboardComponent {
  const w = clamp(component.w, 3, 12)
  return {
    ...component,
    w,
    h: clamp(component.h, 4, 24),
    x: clamp(component.x, 0, 12 - w),
    y: Math.max(0, Math.round(component.y)),
  }
}

export function componentsOverlap(a: DashboardComponent, b: DashboardComponent) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

export function resolveDashboardLayout(
  components: DashboardComponent[],
  priorityId?: string,
): DashboardComponent[] {
  const normalized = components.map(clampComponent)
  const priority = priorityId ? normalized.find((item) => item.id === priorityId) : undefined
  const rest = normalized
    .filter((item) => item.id !== priorityId)
    .sort((a, b) => a.y - b.y || a.x - b.x)
  const placed: DashboardComponent[] = priority ? [priority] : []

  for (const item of rest) {
    let candidate = item
    let overlaps = placed.filter((placedItem) => componentsOverlap(candidate, placedItem))
    while (overlaps.length > 0) {
      candidate = { ...candidate, y: Math.max(...overlaps.map((entry) => entry.y + entry.h)) }
      overlaps = placed.filter((placedItem) => componentsOverlap(candidate, placedItem))
    }
    placed.push(candidate)
  }
  return normalized.map((item) => placed.find((placedItem) => placedItem.id === item.id) ?? item)
}

export function findAvailablePosition(components: DashboardComponent[], w = 6, h = 8) {
  for (let y = 0; y < 1000; y += 1) {
    for (let x = 0; x <= 12 - w; x += 1) {
      const candidate = { id: '__candidate__', title: '', code: '', x, y, w, h }
      if (!components.some((item) => componentsOverlap(candidate, item))) return { x, y }
    }
  }
  return { x: 0, y: Math.max(0, ...components.map((item) => item.y + item.h)) }
}

function dateStringInTimeZone(date: Date, timezone: string) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

export type DashboardDatePreset = 'today' | 'yesterday' | 'last_7_days' | 'last_30_days' | 'this_week' | 'this_month' | 'this_quarter' | 'this_year'

export function dashboardDatePresetRange(preset: DashboardDatePreset, timezone: string) {
  const todayText = dateStringInTimeZone(new Date(), timezone)
  const end = new Date(`${todayText}T00:00:00Z`)
  const start = new Date(end)
  if (preset === 'yesterday') { start.setUTCDate(start.getUTCDate() - 1); end.setUTCDate(end.getUTCDate() - 1) }
  if (preset === 'last_7_days') start.setUTCDate(start.getUTCDate() - 6)
  if (preset === 'last_30_days') start.setUTCDate(start.getUTCDate() - 29)
  if (preset === 'this_week') start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7))
  if (preset === 'this_month') start.setUTCDate(1)
  if (preset === 'this_quarter') { start.setUTCMonth(Math.floor(start.getUTCMonth() / 3) * 3, 1) }
  if (preset === 'this_year') { start.setUTCMonth(0, 1) }
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) }
}

export function defaultDashboardFilterValues(filters: DashboardFilter[], timezone: string) {
  const values: Record<string, unknown> = {}
  for (const filter of filters) {
    if (filter.type === 'date_range') {
      values[filter.id] = dashboardDatePresetRange('last_30_days', timezone)
    } else if (filter.default_value !== undefined && filter.default_value !== null) {
      values[filter.id] = filter.default_value
    }
  }
  return values
}

export function parseDashboardFilterValues(
  raw: string | null,
  filters: DashboardFilter[],
): { values: Record<string, unknown>; invalid: boolean } {
  if (!raw) return { values: {}, invalid: false }
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { values: {}, invalid: true }
    const config = new Map(filters.map((filter) => [filter.id, filter]))
    const values: Record<string, unknown> = {}
    let invalid = false
    for (const [id, value] of Object.entries(parsed)) {
      const filter = config.get(id)
      if (!filter) { invalid = true; continue }
      if (filter.type === 'date_range') {
        const range = value as { start?: unknown; end?: unknown }
        if (!range || typeof range.start !== 'string' || typeof range.end !== 'string') { invalid = true; continue }
        const start = Date.parse(range.start)
        const end = Date.parse(range.end)
        if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || end - start > 366 * 86400000) { invalid = true; continue }
        values[id] = { start: range.start, end: range.end }
      } else if (typeof value === 'string' || typeof value === 'number' || Array.isArray(value) || value === null) {
        values[id] = value
      } else invalid = true
    }
    return { values, invalid }
  } catch {
    return { values: {}, invalid: true }
  }
}

export function sanitizeDashboardFilterValues(
  values: Record<string, unknown>,
  filters: DashboardFilter[],
  fields: UnifiedField[],
) {
  const sanitized = { ...values }
  let invalid = false
  for (const filter of filters) {
    if (filter.type !== 'field_option' || !filter.field_key || sanitized[filter.id] == null) continue
    const [source, key] = filter.field_key.split(':', 2)
    const field = fields.find((item) => item.source === source && item.key === key)
    if (!field) { delete sanitized[filter.id]; invalid = true; continue }
    if (field.field_type === 'employee_select' || field.field_type === 'group_select') continue
    const config = field.type_config as { options?: Array<{ value: string }> }
    const hasDefinedOptions = field.options.length > 0
      || field.tree_nodes.length > 0
      || (config.options?.length ?? 0) > 0
    const allowed = new Set([
      ...field.options.filter((option) => option.is_active).map((option) => String(option.value)),
      ...field.tree_nodes.filter((node) => node.is_active).map((node) => String(node.value)),
      ...(config.options ?? []).map((option) => String(option.value)),
    ])
    if (!hasDefinedOptions) continue
    const current = Array.isArray(sanitized[filter.id]) ? sanitized[filter.id] as unknown[] : [sanitized[filter.id]]
    const valid = current.filter((item) => allowed.has(String(item)))
    if (valid.length !== current.length) invalid = true
    if (valid.length === 0) delete sanitized[filter.id]
    else sanitized[filter.id] = filter.multiple ? valid : valid[0]
  }
  return { values: sanitized, invalid }
}

function fieldCondition(ref: string, operator: string, value: unknown, fields: UnifiedField[]): ConditionItem | null {
  const [source, key] = ref.split(':', 2)
  if (!key || !['system', 'custom', 'metadata'].includes(source)) return null
  if (source === 'custom') {
    const field = fields.find((item) => item.source === 'custom' && item.key === key)
    if (!field?.id) return null
    return { field_id: field.id, field_key: null, operator, value: value as ConditionItem['value'] }
  }
  return { field_id: null, field_key: key, operator, value: value as ConditionItem['value'] }
}

function conditionsFromWhere(where: Record<string, unknown>, fields: UnifiedField[]) {
  const conditions: ConditionItem[] = []
  for (const [ref, rawCondition] of Object.entries(where)) {
    const operators = rawCondition && typeof rawCondition === 'object' && !Array.isArray(rawCondition)
      ? rawCondition as Record<string, unknown>
      : { eq: rawCondition }
    for (const [operator, value] of Object.entries(operators)) {
      const condition = fieldCondition(ref, operator, value, fields)
      if (condition) conditions.push(condition)
    }
  }
  return conditions
}

export function buildDashboardDrilldownConditions(
  output: Record<string, unknown>,
  filters: DashboardFilter[],
  filterValues: Record<string, unknown>,
  fields: UnifiedField[],
) {
  const where: Record<string, unknown> = {}
  for (const filter of filters) {
    const value = filterValues[filter.id]
    if (filter.type === 'date_range' && value && typeof value === 'object') {
      const range = value as { start?: string; end?: string }
      for (const key of filter.field_keys ?? []) where[key] = { gte: range.start, lte: range.end }
    } else if (filter.type === 'field_option' && filter.field_key && value !== undefined && value !== null && value !== '') {
      where[filter.field_key] = { in: Array.isArray(value) ? value : [value] }
    }
  }
  const drilldown = output.drilldown
  if (drilldown && typeof drilldown === 'object' && !Array.isArray(drilldown)) {
    const data = drilldown as Record<string, unknown>
    const additional = (data.where ?? data.filters ?? data) as Record<string, unknown>
    if (additional && typeof additional === 'object' && !Array.isArray(additional)) Object.assign(where, additional)
  }
  return conditionsFromWhere(where, fields)
}

export function buildDashboardDrilldownUrl(
  dashboardId: number,
  conditions: ConditionItem[],
  filterValues?: Record<string, unknown>,
) {
  const params = new URLSearchParams({
    from: 'dashboard',
    dashboardId: String(dashboardId),
    filters: JSON.stringify(conditions),
  })
  if (filterValues) params.set('dashboardFilterValues', JSON.stringify(filterValues))
  return `/workspace/tickets?${params.toString()}`
}
