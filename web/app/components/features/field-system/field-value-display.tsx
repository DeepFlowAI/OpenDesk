'use client'

import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/utils'
import { FieldType } from '@/types/field-enums'
import type { FdFieldOption, FdTreeNode } from '@/models/field-definition'
import { FieldOptionPill, coalescePillOptions } from '@/app/components/features/field-system/field-select-pill-editors'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'
import { useUser } from '@/service/use-users'
import { useOrganization } from '@/service/use-organizations'
import { useEmployee } from '@/service/use-employees'
import { useEmployeeGroup } from '@/service/use-employee-groups'
import { FieldFileDisplay } from '@/app/components/features/field-system/field-file-display'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { SafeHtml } from '@/components/safe-html'

type FieldValueDisplayProps = {
  fieldType: FieldType
  value: unknown
  typeConfig?: Record<string, unknown>
  options?: FdFieldOption[]
  treeNodes?: FdTreeNode[]
  className?: string
}

/**
 * Read-only renderer for a field value.
 * Used in tables, detail views, and workspace panels.
 */
export function FieldValueDisplay({
  fieldType,
  value,
  typeConfig = {},
  options = [],
  treeNodes = [],
  className,
}: FieldValueDisplayProps) {
  if (value === null || value === undefined || value === '') {
    return <span className={cn('text-muted-foreground', className)}>—</span>
  }

  switch (fieldType) {
    case FieldType.SINGLE_LINE_TEXT:
    case FieldType.MULTI_LINE_TEXT:
      if (typeConfig.value_kind === 'actor') {
        return (
          <span className={cn('min-w-0 max-w-full break-words', className)}>{formatActorFieldValue(value)}</span>
        )
      }
      return <span className={cn('min-w-0 max-w-full whitespace-pre-wrap break-words', className)}>{String(value)}</span>

    case FieldType.NUMBER: {
      const num = Number(value)
      const decimals = (typeConfig.decimal_places as number) ?? 0
      const suffix = (typeConfig.unit_suffix as string) ?? ''
      return (
        <span className={cn('tabular-nums', className)}>
          {num.toFixed(decimals)}
          {suffix && <span className="ml-0.5 text-muted-foreground">{suffix}</span>}
        </span>
      )
    }

    case FieldType.DATE:
      return <span className={className}>{String(value)}</span>

    case FieldType.TIME:
      return <span className={cn('tabular-nums', className)}>{String(value)}</span>

    case FieldType.DATETIME: {
      return (
        <span className={cn('tabular-nums', className)}>{formatDatetimeForDisplay(String(value))}</span>
      )
    }

    case FieldType.SINGLE_SELECT: {
      const pool = coalescePillOptions(options, typeConfig)
      const opt = pool.find((o) => o.value === String(value))
      if (!opt) return <span className={className}>{String(value)}</span>
      return (
        <span className={cn('inline-flex items-center', className)}>
          <FieldOptionPill label={opt.label} color={opt.color} />
        </span>
      )
    }

    case FieldType.MULTI_SELECT: {
      let ids: string[] = []
      if (Array.isArray(value)) ids = value as string[]
      else if (typeof value === 'string' && value) ids = value.split(',').map((s) => s.trim()).filter(Boolean)
      const pool = coalescePillOptions(options, typeConfig)
      const matched = ids.map((id) => pool.find((o) => o.value === id)).filter(Boolean)
      if (matched.length === 0) return <span className={cn('text-muted-foreground', className)}>—</span>
      return (
        <span className={cn('inline-flex flex-wrap items-center gap-1.5', className)}>
          {matched.map((opt) => (
            <FieldOptionPill key={opt!.value} label={opt!.label} color={opt!.color} />
          ))}
        </span>
      )
    }

    case FieldType.SINGLE_SELECT_TREE: {
      const node = treeNodes.find((n) => n.value === String(value))
      return <span className={className}>{node ? node.label : String(value)}</span>
    }

    case FieldType.MULTI_SELECT_TREE: {
      const ids = Array.isArray(value) ? (value as string[]) : []
      const matched = ids.map((id) => treeNodes.find((n) => n.value === id)).filter(Boolean)
      if (matched.length === 0) return <span className={cn('text-muted-foreground', className)}>—</span>
      return (
        <span className={cn('inline-flex flex-wrap gap-1', className)}>
          {matched.map((n) => (
            <span key={n!.id} className="rounded-md bg-muted px-2 py-0.5 text-xs">
              {n!.label}
            </span>
          ))}
        </span>
      )
    }

    case FieldType.EMAIL:
      return (
        <a href={`mailto:${String(value)}`} className={cn('text-primary underline-offset-2 hover:underline', className)}>
          {String(value)}
        </a>
      )

    case FieldType.PHONE:
      return (
        <a href={`tel:${String(value)}`} className={cn('tabular-nums text-primary underline-offset-2 hover:underline', className)}>
          {String(value)}
        </a>
      )

    case FieldType.URL: {
      const s = String(value)
      return (
        <a
          href={s}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            'inline-block max-w-full break-words text-blue-600 underline-offset-2 hover:text-blue-800 hover:underline dark:text-blue-400 dark:hover:text-blue-300',
            className,
          )}
        >
          {s}
        </a>
      )
    }

    case FieldType.FILE: {
      return <FieldFileDisplay value={value} className={className} />
    }

    case FieldType.RICH_TEXT: {
      const fmt = ((typeConfig.rich_format as string) ?? 'html').toLowerCase()
      if (fmt === 'markdown') {
        return (
          <div
            className={cn(
              'prose prose-sm dark:prose-invert max-w-none min-w-0 break-words',
              richTextListStyleClass,
              className,
            )}
          >
            <ReactMarkdown>{String(value)}</ReactMarkdown>
          </div>
        )
      }
      return (
        <SafeHtml
          html={String(value)}
          className={cn(
            'prose prose-sm dark:prose-invert max-w-none min-w-0 break-words',
            richTextListStyleClass,
            className,
          )}
        />
      )
    }

    case FieldType.ORGANIZATION_SELECT:
      return <OrganizationValueDisplay value={value} className={className} />

    case FieldType.USER_SELECT:
      return <UserValueDisplay value={value} className={className} />

    case FieldType.EMPLOYEE_SELECT:
      return <EmployeeValueDisplay value={value} className={className} />

    case FieldType.GROUP_SELECT:
      return <EmployeeGroupValueDisplay value={value} className={className} />

    default:
      return <span className={cn('min-w-0 max-w-full break-words', className)}>{String(value)}</span>
  }
}

export function formatActorFieldValue(value: unknown): string {
  if (value == null || value === '') return '—'
  if (typeof value === 'object' && !Array.isArray(value)) {
    const actor = value as {
      actor_type?: unknown
      actor_id?: unknown
      actor_name?: unknown
    }
    if (typeof actor.actor_name === 'string' && actor.actor_name.trim()) {
      return actor.actor_name.trim()
    }
    const type = typeof actor.actor_type === 'string' && actor.actor_type.trim()
      ? actor.actor_type.trim()
      : 'actor'
    if (actor.actor_id != null && actor.actor_id !== '') {
      return `${type} #${String(actor.actor_id)}`
    }
    return type
  }
  return String(value)
}

function OrganizationValueDisplay({ value, className }: { value: unknown; className?: string }) {
  const organizationId = typeof value === 'number' ? value : Number(value)
  const { data: organization } = useOrganization(Number.isFinite(organizationId) ? organizationId : 0)
  return <span className={className}>{organization?.name ?? String(value)}</span>
}

function UserValueDisplay({ value, className }: { value: unknown; className?: string }) {
  const userId = typeof value === 'number' ? value : Number(value)
  const { data: user } = useUser(Number.isFinite(userId) ? userId : 0)
  const label = user?.name || String(value)
  return <span className={className}>{label}</span>
}

function EmployeeValueDisplay({ value, className }: { value: unknown; className?: string }) {
  const employeeId = typeof value === 'number' ? value : Number(value)
  const { data: employee } = useEmployee(Number.isFinite(employeeId) ? employeeId : 0)
  const label = employee?.nickname || employee?.name || employee?.username || String(value)
  return <span className={className}>{label}</span>
}

function EmployeeGroupValueDisplay({ value, className }: { value: unknown; className?: string }) {
  const groupId = typeof value === 'number' ? value : Number(value)
  const { data: group } = useEmployeeGroup(Number.isFinite(groupId) ? groupId : 0)
  return <span className={className}>{group?.name ?? String(value)}</span>
}

/**
 * Plain-text file labels for table cells and other non-React display paths.
 * Attachment values are objects ({ url, name }); coercing them with String() yields "[object Object]".
 */
export function formatFileFieldValue(value: unknown, isZh: boolean): string {
  if (value == null || value === '') return ''
  const files = Array.isArray(value) ? value : [value]
  const labels = files
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object' && !Array.isArray(item))
    .map((f, i) => {
      const n = f.name
      if (typeof n === 'string' && n) return n
      return isZh ? `文件 ${i + 1}` : `File ${i + 1}`
    })
  return labels.join(isZh ? '、' : ', ')
}
