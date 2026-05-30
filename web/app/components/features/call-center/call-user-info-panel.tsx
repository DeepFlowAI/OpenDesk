'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRouter } from 'next/navigation'
import { IconLoader2 } from '@tabler/icons-react'

import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { CallRecordUserBrief } from '@/models/call-center'
import type { CustomFieldValue, UpdateUserPayload, User } from '@/models/user'
import type { UnifiedField } from '@/models/field-definition'
import {
  useCallRecord,
  useIdentifyCallRecordUser,
  useLinkCallRecordUser,
} from '@/service/use-call-center'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useUpdateUser, useUser } from '@/service/use-users'
import { FieldType } from '@/types/field-enums'

type Props = {
  recordId: number | null | undefined
  fallbackNumber: string
}

const SYSTEM_KEY_ALIAS: Record<string, keyof User> = { nickname: 'name' }
const EDITABLE_SYSTEM_KEYS = new Set(['name', 'email', 'phone', 'gender', 'address', 'remark', 'web_id', 'organization_id'])
const READONLY_FIELD_KEYS = new Set(['id', 'public_id', 'external_id', 'created_at', 'updated_at', 'channel_id'])
const INSTANT_SAVE_FIELD_TYPES = new Set<FieldType>([
  FieldType.SINGLE_SELECT,
  FieldType.MULTI_SELECT,
  FieldType.SINGLE_SELECT_TREE,
  FieldType.MULTI_SELECT_TREE,
  FieldType.FILE,
  FieldType.ORGANIZATION_SELECT,
])

export function CallUserInfoPanel({ recordId, fallbackNumber }: Props) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const recordQuery = useCallRecord(recordId)
  const identifyUser = useIdentifyCallRecordUser()
  const linkUser = useLinkCallRecordUser()
  const attemptedIdentifyRef = useRef<number | null>(null)

  const record = recordQuery.data ?? null
  const associatedUserRef = record?.user_public_id ?? record?.user_id ?? null
  const userQuery = useUser(associatedUserRef)
  const fieldsQuery = useUnifiedFields({ domain: 'user', locale, include_metadata: false })
  const updateUser = useUpdateUser()

  useEffect(() => {
    if (!recordId || !record || record.user_association_status !== 'unlinked') return
    if (attemptedIdentifyRef.current === recordId) return
    attemptedIdentifyRef.current = recordId
    identifyUser.mutate(recordId)
  }, [recordId, record, identifyUser])

  const workspaceFields = useMemo(
    () =>
      (fieldsQuery.data?.items ?? [])
        .filter((field) => field.source !== 'metadata' && field.status === 'active' && field.show_in_workspace === true)
        .sort((a, b) => a.sort_order - b.sort_order),
    [fieldsQuery.data?.items],
  )

  const status = record?.user_association_status ?? (fallbackNumber ? 'unlinked' : 'unknown')
  const canViewUser = !!associatedUserRef && (status === 'linked' || status === 'created')

  return (
    <div className="space-y-4">
      <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-2">
        <h3 className="text-sm font-semibold">用户信息</h3>
        {canViewUser && (
          <button
            type="button"
            onClick={() => router.push(`/workspace/users/${associatedUserRef}`)}
            className="shrink-0 text-xs font-medium text-primary underline-offset-2 hover:underline"
          >
            详情
          </button>
        )}
      </div>

      {status === 'created' && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
          已根据号码新建用户
        </p>
      )}

      {!recordId ? (
        <PanelStateMessage>{fallbackNumber ? '等待通话记录生成后匹配用户' : '无法根据未知号码关联用户'}</PanelStateMessage>
      ) : recordQuery.isLoading ? (
        <PanelStateMessage>用户信息加载中...</PanelStateMessage>
      ) : recordQuery.isError || identifyUser.isError ? (
        <RetryState
          message="用户识别失败，请重试"
          onRetry={() => {
            attemptedIdentifyRef.current = null
            if (recordId) identifyUser.mutate(recordId)
            void recordQuery.refetch()
          }}
        />
      ) : status === 'unknown' ? (
        <PanelStateMessage>无法根据未知号码关联用户</PanelStateMessage>
      ) : status === 'multiple' ? (
        <CandidateList
          candidates={record?.associated_user_candidates ?? []}
          isSaving={linkUser.isPending}
          onSelect={(userId) => {
            if (!recordId) return
            linkUser.mutate({ recordId, userId })
          }}
        />
      ) : userQuery.isLoading || fieldsQuery.isLoading ? (
        <PanelStateMessage>用户信息加载中...</PanelStateMessage>
      ) : userQuery.isError || fieldsQuery.isError ? (
        <RetryState
          message="加载用户信息失败"
          onRetry={() => {
            void userQuery.refetch()
            void fieldsQuery.refetch()
          }}
        />
      ) : userQuery.data ? (
        <EditableUserFields
          locale={locale}
          user={userQuery.data}
          fields={workspaceFields}
          isSaving={updateUser.isPending}
          onSave={(field, value) =>
            updateUser.mutateAsync({
              id: userQuery.data.id,
              data: buildUpdatePayload(field, value),
            })
          }
        />
      ) : (
        <PanelStateMessage>当前通话暂未关联用户</PanelStateMessage>
      )}
    </div>
  )
}

function CandidateList({
  candidates,
  isSaving,
  onSelect,
}: {
  candidates: CallRecordUserBrief[]
  isSaving: boolean
  onSelect: (userId: number) => void
}) {
  if (candidates.length === 0) {
    return <PanelStateMessage>该号码匹配到多个用户，请刷新后选择关联用户</PanelStateMessage>
  }
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">该号码匹配到多个用户，请选择本次通话关联的用户</p>
      {candidates.map((candidate) => (
        <button
          key={candidate.id}
          type="button"
          disabled={isSaving}
          onClick={() => onSelect(candidate.id)}
          className="flex w-full items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-60"
        >
          <span className="min-w-0 truncate font-medium">{candidate.name || candidate.public_id}</span>
          <span className="shrink-0 text-xs text-muted-foreground">{candidate.phone || candidate.email || candidate.public_id}</span>
        </button>
      ))}
    </div>
  )
}

function EditableUserFields({
  locale,
  user,
  fields,
  isSaving,
  onSave,
}: {
  locale: Locale
  user: User
  fields: UnifiedField[]
  isSaving: boolean
  onSave: (field: UnifiedField, value: unknown) => Promise<unknown>
}) {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState<unknown>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)

  if (fields.length === 0) {
    return <PanelStateMessage>暂无展示字段，请在用户字段中配置在工作台展示</PanelStateMessage>
  }

  const startEdit = (field: UnifiedField) => {
    if (!isFieldEditable(field)) return
    setEditingKey(getFieldIdentity(field))
    setDraftValue(getFieldRawValue(user, field))
    setFieldError(null)
  }

  const cancelEdit = () => {
    setEditingKey(null)
    setDraftValue(null)
    setFieldError(null)
  }

  const saveEdit = async (field: UnifiedField, submittedValue: unknown = draftValue) => {
    const originalValue = getFieldRawValue(user, field)
    if (areFieldValuesEqual(originalValue, submittedValue)) {
      cancelEdit()
      return
    }
    const validationError = validateFieldValue(field, submittedValue)
    if (validationError) {
      setFieldError(validationError)
      return
    }
    try {
      await onSave(field, submittedValue)
      cancelEdit()
    } catch {
      setDraftValue(originalValue)
      setFieldError('保存失败，请重试')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {fields.map((field) => {
        const identity = getFieldIdentity(field)
        const editing = editingKey === identity
        const editable = isFieldEditable(field)
        return (
          <EditableInfoRow
            key={identity}
            field={field}
            value={editing ? draftValue : getFieldRawValue(user, field)}
            editing={editing}
            editable={editable}
            saving={editing && isSaving}
            error={editing ? fieldError : null}
            locale={locale}
            onEdit={() => startEdit(field)}
            onChange={setDraftValue}
            onCancel={cancelEdit}
            onSave={() => saveEdit(field)}
            onSaveValue={(value) => saveEdit(field, value)}
          />
        )
      })}
    </div>
  )
}

function EditableInfoRow({
  field,
  value,
  editing,
  editable,
  saving,
  error,
  locale,
  onEdit,
  onChange,
  onCancel,
  onSave,
  onSaveValue,
}: {
  field: UnifiedField
  value: unknown
  editing: boolean
  editable: boolean
  saving: boolean
  error: string | null
  locale: Locale
  onEdit: () => void
  onChange: (value: unknown) => void
  onCancel: () => void
  onSave: () => void
  onSaveValue: (value: unknown) => void
}) {
  const shouldSaveOnChange = INSTANT_SAVE_FIELD_TYPES.has(field.field_type)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className="text-[12px] text-muted-foreground">{field.name}</span>
        {field.help_text && <FieldHelpTooltip text={field.help_text} />}
      </div>

      {editing ? (
        <div
          onBlurCapture={(event) => {
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
            if (field.field_type === FieldType.FILE) return
            void onSave()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              onCancel()
            }
            if (event.key === 'Enter' && field.field_type !== FieldType.MULTI_LINE_TEXT && !INSTANT_SAVE_FIELD_TYPES.has(field.field_type)) {
              event.preventDefault()
              void onSave()
            }
          }}
        >
          <div className="relative">
            <UnifiedFieldValueEditor
              field={field}
              value={value}
              onChange={(nextValue) => {
                onChange(nextValue)
                if (shouldSaveOnChange) void onSaveValue(nextValue)
              }}
              disabled={saving}
              className="min-h-8 text-[13px]"
              autoFocus
            />
            {saving && <IconLoader2 size={14} className="absolute right-2 top-2.5 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
        </div>
      ) : (
        <button
          type="button"
          onClick={onEdit}
          disabled={!editable}
          className={cn(
            'min-h-5 max-w-full rounded-sm text-left text-[13px] text-foreground outline-none',
            editable && 'cursor-text hover:bg-black/[0.04] focus-visible:ring-2 focus-visible:ring-ring',
            !editable && 'cursor-default',
          )}
          aria-label={editable ? `编辑字段 ${field.name}` : field.name}
        >
          <FieldValueDisplay
            fieldType={field.field_type}
            value={value}
            typeConfig={field.type_config ?? {}}
            options={field.options}
            treeNodes={field.tree_nodes}
            className="break-words text-[13px]"
          />
        </button>
      )}
    </div>
  )
}

function FieldHelpTooltip({ text }: { text: string }) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)

  const showTooltip = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const tooltipWidth = 176
    const viewportMargin = 8
    const left = Math.min(
      Math.max(rect.left + rect.width / 2 - tooltipWidth / 2, viewportMargin),
      window.innerWidth - tooltipWidth - viewportMargin,
    )
    setPosition({ left, top: rect.bottom + 6 })
    setOpen(true)
  }

  return (
    <>
      <span
        ref={triggerRef}
        tabIndex={0}
        onMouseEnter={showTooltip}
        onMouseLeave={() => setOpen(false)}
        onFocus={showTooltip}
        onBlur={() => setOpen(false)}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-border text-[10px] text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        ?
      </span>
      {open &&
        position &&
        createPortal(
          <span
            className="pointer-events-none fixed z-[100] w-44 rounded-md border border-border bg-popover px-2 py-1.5 text-left text-xs text-popover-foreground shadow-md"
            style={{ left: position.left, top: position.top }}
          >
            {text}
          </span>,
          document.body,
        )}
    </>
  )
}

function RetryState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
      <p className="text-xs text-destructive">{message}</p>
      <button type="button" onClick={onRetry} className="mt-2 text-xs font-medium text-primary hover:underline">
        重试
      </button>
    </div>
  )
}

function PanelStateMessage({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
      <p className="text-xs text-muted-foreground">{children}</p>
    </div>
  )
}

function getFieldIdentity(field: UnifiedField): string {
  return field.key ?? `custom:${field.id ?? field.name}`
}

function getSystemKey(field: UnifiedField): keyof User | null {
  if (field.source === 'custom') return null
  if (!field.key) return null
  return SYSTEM_KEY_ALIAS[field.key] ?? (field.key as keyof User)
}

function getFieldRawValue(user: User, field: UnifiedField): unknown {
  const systemKey = getSystemKey(field)
  if (systemKey) return user[systemKey]
  if (field.key) return user.custom_fields?.[field.key] ?? (field.id != null ? user.custom_fields?.[String(field.id)] : null)
  if (field.id != null) return user.custom_fields?.[String(field.id)] ?? null
  return null
}

function isFieldEditable(field: UnifiedField): boolean {
  if (field.source === 'custom') return field.id != null
  if (!field.key || READONLY_FIELD_KEYS.has(field.key)) return false
  const systemKey = getSystemKey(field)
  return !!systemKey && EDITABLE_SYSTEM_KEYS.has(systemKey)
}

function buildUpdatePayload(field: UnifiedField, value: unknown): UpdateUserPayload {
  const systemKey = getSystemKey(field)
  if (systemKey && EDITABLE_SYSTEM_KEYS.has(systemKey)) {
    return { [systemKey]: normalizeEmptyValue(value) } as UpdateUserPayload
  }
  const customKey = field.key ?? (field.id != null ? String(field.id) : null)
  if (customKey) {
    return { custom_fields: { [customKey]: normalizeEmptyValue(value) as CustomFieldValue } }
  }
  return {}
}

function normalizeEmptyValue(value: unknown): unknown {
  return value === '' ? null : value
}

function areFieldValuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(normalizeEmptyValue(a)) === JSON.stringify(normalizeEmptyValue(b))
}

function validateFieldValue(field: UnifiedField, value: unknown): string | null {
  const required = (field.type_config?.required as boolean | undefined) === true
  const normalized = normalizeEmptyValue(value)
  if (required && (normalized === null || normalized === undefined)) {
    return '该字段为必填'
  }
  if (field.field_type === FieldType.EMAIL && typeof normalized === 'string' && normalized) {
    const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)
    if (!valid) return '格式不正确'
  }
  return null
}
