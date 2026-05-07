'use client'

import Link from 'next/link'
import type { EntityChange, EntityChangeValue } from '@/models/entity-change'
import type { UnifiedField } from '@/models/field-definition'
import { FieldType } from '@/types/field-enums'
import { useOrganization } from '@/service/use-organizations'
import { formatActorFieldValue } from '@/app/components/features/field-system/field-value-display'
import { ActivityActorAvatar } from '@/app/components/features/ticket/activity-actor-avatar'
import {
  ActivityTimeline,
  ActivityTimelineRow,
} from '@/app/components/features/ticket/activity-timeline-row'
import { richTextToPlainCell } from '@/lib/rich-text-plain'
import { buildSelectLookup } from '@/lib/workspace-group'

const ENTITY_CHANGE_CREATE_FIELD_KEY = '__create__'

export function EntityChangeTimeline({
  changes,
  isLoading,
  isError,
  isZh,
  resolveFieldDef,
  emptyText,
  showRail = true,
}: {
  changes: EntityChange[]
  isLoading: boolean
  isError: boolean
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
  emptyText: string
  showRail?: boolean
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-muted-foreground">
          {isZh ? '加载动态中...' : 'Loading activity...'}
        </p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-destructive">
          {isZh ? '动态加载失败' : 'Failed to load activity'}
        </p>
      </div>
    )
  }

  if (changes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 text-center">
        <p className="text-xs text-muted-foreground">{emptyText}</p>
      </div>
    )
  }

  return (
    <ActivityTimeline showRail={showRail}>
      {changes.map((change) => (
        <ActivityTimelineRow key={change.id}>
          <EntityChangeCard
            change={change}
            isZh={isZh}
            resolveFieldDef={resolveFieldDef}
          />
        </ActivityTimelineRow>
      ))}
    </ActivityTimeline>
  )
}

export function EntityChangeCard({
  change,
  isZh,
  resolveFieldDef,
}: {
  change: EntityChange
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
}) {
  const actorName = getChangeActorName(change, isZh)
  const isCreateRecord = change.field_key === ENTITY_CHANGE_CREATE_FIELD_KEY

  return (
    <div className="rounded-lg bg-white px-4 py-3.5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <ActivityActorAvatar name={actorName} src={change.actor_avatar} />
          <span className="min-w-0 truncate text-[13px] text-foreground">
            {actorName}
          </span>
        </div>
        <time
          className="shrink-0 text-xs text-muted-foreground"
          dateTime={change.created_at}
        >
          {formatChangeTime(change.created_at, isZh)}
        </time>
      </div>
      {change.entries && change.entries.length > 0 ? (
        <div className="flex flex-col gap-3">
          {change.entries.map((entry, idx) => (
            <div
              key={`${change.id}-${entry.field_key}-${idx}`}
              className="text-xs leading-relaxed text-foreground"
            >
              {isCreateRecord ? (
                <>
                  <span>{entry.field_label}</span>
                  <span className="mx-1">:</span>
                  <ChangeValuePill
                    value={entry.new_value}
                    fieldKey={entry.field_key}
                    fieldDef={resolveFieldDef(entry.field_key)}
                    isZh={isZh}
                  />
                </>
              ) : (
                <>
                  <span>{entry.field_label}</span>
                  <span className="mx-1">{isZh ? '从' : 'from'}</span>
                  <ChangeValuePill
                    value={entry.old_value}
                    fieldKey={entry.field_key}
                    fieldDef={resolveFieldDef(entry.field_key)}
                    isZh={isZh}
                  />
                  <span className="mx-1">{isZh ? '变更为' : 'to'}</span>
                  <ChangeValuePill
                    value={entry.new_value}
                    fieldKey={entry.field_key}
                    fieldDef={resolveFieldDef(entry.field_key)}
                    isZh={isZh}
                  />
                </>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-foreground">
          <span>{change.field_label}</span>
          <span className="mx-1">{isZh ? '从' : 'from'}</span>
          <ChangeValuePill
            value={change.old_value}
            fieldKey={change.field_key}
            fieldDef={resolveFieldDef(change.field_key)}
            isZh={isZh}
          />
          <span className="mx-1">{isZh ? '变更为' : 'to'}</span>
          <ChangeValuePill
            value={change.new_value}
            fieldKey={change.field_key}
            fieldDef={resolveFieldDef(change.field_key)}
            isZh={isZh}
          />
        </div>
      )}
    </div>
  )
}

function ChangeValuePill({
  value,
  fieldKey,
  fieldDef,
  isZh,
}: {
  value: EntityChangeValue
  fieldKey: string
  fieldDef: UnifiedField | undefined
  isZh: boolean
}) {
  if (fieldKey === 'organization_id' || fieldDef?.field_type === FieldType.ORGANIZATION_SELECT) {
    return <OrganizationChangeValue value={value} isZh={isZh} />
  }

  return (
    <span className="rounded-md bg-muted px-1.5 py-0.5">
      {formatChangeValue(value, fieldKey, fieldDef, isZh)}
    </span>
  )
}

function OrganizationChangeValue({
  value,
  isZh,
}: {
  value: EntityChangeValue
  isZh: boolean
}) {
  const orgValue = parseEntityId(value)
  const { data: org } = useOrganization(orgValue ?? 0)

  if (!orgValue) {
    return <span className="rounded-md bg-muted px-1.5 py-0.5">-</span>
  }

  const label = org?.name?.trim() || (isZh ? `组织 #${orgValue}` : `Organization #${orgValue}`)

  return (
    <Link
      href={`/workspace/organizations/${orgValue}`}
      className="rounded-md bg-muted px-1.5 py-0.5 font-medium text-primary underline-offset-2 hover:underline"
    >
      {label}
    </Link>
  )
}

function parseEntityId(value: EntityChangeValue): number | null {
  if (value == null || value === '') return null
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const id = Number(value)
    return Number.isFinite(id) && id > 0 ? id : null
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    const rawId = (value as { id?: unknown }).id
    const id = typeof rawId === 'number' ? rawId : Number(rawId)
    return Number.isFinite(id) && id > 0 ? id : null
  }
  return null
}

function formatChangeTime(value: string, isZh: boolean): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function getChangeActorName(change: EntityChange, isZh: boolean): string {
  if (change.actor_type === 'user' && change.actor_id != null) {
    return change.actor_name?.trim() || (isZh ? '未命名' : 'Unnamed')
  }
  return change.actor_name?.trim() || (isZh ? '系统' : 'System')
}

function formatChangeValue(
  value: EntityChangeValue,
  fieldKey: string,
  fieldDef: UnifiedField | undefined,
  isZh: boolean,
): string {
  if (value == null || value === '') return '-'
  const raw = String(value)

  const fieldType = fieldDef?.field_type
  if (fieldDef?.type_config?.value_kind === 'actor') {
    return formatActorFieldValue(value)
  }
  if (fieldKey === 'description' || fieldType === FieldType.RICH_TEXT) {
    const plain = richTextToPlainCell(value, fieldDef?.type_config)
    return plain === '' ? '-' : plain
  }

  const selectLookup = buildSelectLookup(fieldDef)
  if (selectLookup) {
    if (Array.isArray(value)) {
      if (value.length === 0) return '-'
      return value.map((item) => applySelectLookupString(String(item), selectLookup)).join(isZh ? '、' : ', ')
    }
    if (typeof value === 'string' || typeof value === 'number') {
      return applySelectLookupString(String(value), selectLookup)
    }
  }

  if (typeof value === 'boolean') return isZh ? (value ? '是' : '否') : (value ? 'Yes' : 'No')
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    return value.map((item) => {
      if (item && typeof item === 'object' && 'name' in item) {
        const name = (item as { name?: unknown }).name
        return typeof name === 'string' ? name : JSON.stringify(item)
      }
      return typeof item === 'object' ? JSON.stringify(item) : String(item)
    }).join('、')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return raw
}

function applySelectLookupString(raw: string, selectLookup: Map<string, string>): string {
  if (raw.includes(',')) {
    return raw
      .split(',')
      .map((v) => selectLookup.get(v.trim()) ?? v.trim())
      .join(', ')
  }
  return selectLookup.get(raw) ?? raw
}
