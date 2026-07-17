'use client'

import { useEffect, useMemo, useState } from 'react'
import { HTTPError } from 'ky'
import { IconCheck, IconChevronDown, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  useBindableEmployees,
  useCreateSipExtension,
  useSipRegistrationInfo,
  useUpdateSipExtension,
} from '@/service/use-sip-extensions'
import type {
  CreateSipExtensionResponse,
  SipExtension,
} from '@/models/sip-extension'

async function readErrorMessage(error: unknown, fallback: string): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.json()) as { message?: string }
      return body.message || fallback
    } catch {
      return fallback
    }
  }
  return fallback
}

type BoundEmployeeInitial = { id: number; name: string; avatar: string | null } | null

function BindableEmployeeSelect({
  value,
  initialLabel,
  onChange,
  disabled,
}: {
  value: number | null
  initialLabel: string | null
  onChange: (id: number | null) => void
  disabled?: boolean
}) {
  const { locale } = useLocaleStore()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const { data: employees = [], isLoading } = useBindableEmployees(debounced, open)

  const selectedLabel = useMemo(() => {
    if (value == null) return ''
    const match = employees.find((e) => e.id === value)
    return match?.name ?? initialLabel ?? ''
  }, [value, employees, initialLabel])

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'flex h-10 w-full items-center gap-2 rounded-lg border border-border bg-white px-3 text-left text-sm text-foreground outline-none transition-colors focus:border-foreground/40 disabled:cursor-not-allowed disabled:opacity-50',
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate', !selectedLabel && 'text-muted-foreground')}>
          {selectedLabel || t('se.form.employee.placeholder', locale)}
        </span>
        {value != null && !disabled && (
          <span
            role="button"
            tabIndex={0}
            aria-label={t('se.form.employee.clear', locale)}
            onClick={(event) => {
              event.stopPropagation()
              onChange(null)
            }}
            className="rounded text-muted-foreground hover:text-foreground"
          >
            <IconX size={14} />
          </span>
        )}
        <IconChevronDown size={14} className="shrink-0 text-muted-foreground" />
      </button>

      {open && !disabled && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-white p-2 shadow-lg">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('se.form.employee.search', locale)}
            className="mb-2 h-8 w-full rounded-md border border-border bg-white px-2 text-sm outline-none focus:border-foreground/40"
            autoFocus
          />
          <div className="max-h-56 overflow-y-auto">
            {isLoading ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">{t('se.loading', locale)}</div>
            ) : employees.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">{t('se.form.employee.empty', locale)}</div>
            ) : (
              employees.map((employee) => {
                const selected = value === employee.id
                return (
                  <button
                    type="button"
                    key={employee.id}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => {
                      onChange(employee.id)
                      setOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent',
                      selected && 'bg-accent',
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate text-foreground">{employee.name}</span>
                    {selected && <IconCheck size={14} className="shrink-0 text-primary" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function SipExtensionFormDialog({
  open,
  target,
  onClose,
  onCreated,
}: {
  open: boolean
  target: SipExtension | null
  onClose: () => void
  onCreated: (response: CreateSipExtensionResponse) => void
}) {
  const { locale } = useLocaleStore()
  const isEdit = !!target
  const [name, setName] = useState('')
  const [extensionNumber, setExtensionNumber] = useState('')
  const [employeeId, setEmployeeId] = useState<number | null>(null)
  const [initialEmployee, setInitialEmployee] = useState<BoundEmployeeInitial>(null)
  const [nameError, setNameError] = useState('')
  const [numberError, setNumberError] = useState('')
  const [formError, setFormError] = useState('')

  const createMutation = useCreateSipExtension()
  const updateMutation = useUpdateSipExtension()
  const regInfo = useSipRegistrationInfo(isEdit ? (target?.id ?? null) : null)
  const submitting = createMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if (!open) return
    setName(target?.name ?? '')
    setExtensionNumber(target?.extension_number ?? '')
    setEmployeeId(target?.bound_employee_id ?? null)
    setInitialEmployee(target?.bound_employee ?? null)
    setNameError('')
    setNumberError('')
    setFormError('')
  }, [open, target])

  if (!open) return null

  const validate = () => {
    let ok = true
    const trimmedName = name.trim()
    if (trimmedName.length < 1 || trimmedName.length > 50) {
      setNameError(t('se.form.name.error', locale))
      ok = false
    }
    if (!isEdit) {
      if (!/^\d{2,10}$/.test(extensionNumber.trim())) {
        setNumberError(t('se.form.number.error', locale))
        ok = false
      }
    }
    return ok
  }

  const handleSubmit = async () => {
    setFormError('')
    if (!validate()) return
    try {
      if (isEdit && target) {
        await updateMutation.mutateAsync({
          id: target.id,
          data: { name: name.trim(), bound_employee_id: employeeId },
        })
        onClose()
      } else {
        const response = await createMutation.mutateAsync({
          name: name.trim(),
          extension_number: extensionNumber.trim(),
          bound_employee_id: employeeId,
        })
        onCreated(response)
      }
    } catch (error) {
      const message = await readErrorMessage(error, t('se.form.saveFailed', locale))
      // Duplicate extension number surfaces inline on its field.
      if (!isEdit && error instanceof HTTPError && error.response.status === 409) {
        setNumberError(message)
        return
      }
      setFormError(message)
    }
  }

  const secret = regInfo.data
  const maskedRows: { labelKey: string; value: string | null }[] = secret
    ? [
        { labelKey: 'se.reg.server', value: secret.registration_server },
        { labelKey: 'se.reg.port', value: secret.registration_port },
        { labelKey: 'se.reg.transport', value: secret.transport },
        { labelKey: 'se.reg.userId', value: secret.sip_user_id },
        { labelKey: 'se.reg.authAccount', value: secret.auth_account },
        { labelKey: 'se.reg.authPassword', value: secret.auth_password_masked },
      ]
    : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[90vh] w-[560px] max-w-[92vw] overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-foreground">
          {isEdit ? t('se.edit.title', locale) : t('se.create.title', locale)}
        </h2>

        <div className="mt-5 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">{t('se.form.name', locale)}</label>
            <input
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                setNameError('')
              }}
              maxLength={50}
              className="h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none transition-colors focus:border-foreground/40"
              placeholder={t('se.form.name.placeholder', locale)}
            />
            {nameError && <p className="text-xs text-destructive">{nameError}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">{t('se.form.number', locale)}</label>
            <input
              value={extensionNumber}
              onChange={(event) => {
                setExtensionNumber(event.target.value.replace(/\D/g, ''))
                setNumberError('')
              }}
              readOnly={isEdit}
              maxLength={10}
              inputMode="numeric"
              className={cn(
                'h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none transition-colors focus:border-foreground/40',
                isEdit && 'cursor-not-allowed bg-muted/50 text-muted-foreground',
              )}
              placeholder={t('se.form.number.placeholder', locale)}
            />
            {isEdit && <p className="text-xs text-muted-foreground">{t('se.form.number.readonly', locale)}</p>}
            {numberError && <p className="text-xs text-destructive">{numberError}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-foreground">{t('se.form.employee', locale)}</label>
            <BindableEmployeeSelect
              value={employeeId}
              initialLabel={initialEmployee?.name ?? null}
              onChange={setEmployeeId}
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">{t('se.form.employee.hint', locale)}</p>
          </div>

          {isEdit && (
            <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 p-3">
              <p className="text-sm font-medium text-foreground">{t('se.form.regInfo', locale)}</p>
              {regInfo.isLoading ? (
                <p className="text-sm text-muted-foreground">{t('se.loading', locale)}</p>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                  {maskedRows.map((row) => (
                    <div key={row.labelKey} className="contents">
                      <dt className="text-muted-foreground">{t(row.labelKey, locale)}</dt>
                      <dd className="break-all font-mono text-foreground">{row.value || '—'}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          )}

          {formError && <p className="text-sm text-destructive">{formError}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
          >
            {t('se.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:opacity-50"
          >
            {submitting ? '...' : isEdit ? t('se.save', locale) : t('se.create.submit', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}
