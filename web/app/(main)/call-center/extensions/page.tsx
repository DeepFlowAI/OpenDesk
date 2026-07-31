'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { HTTPError } from 'ky'
import {
  IconCopy,
  IconDeviceLandlinePhone,
  IconKey,
  IconPencil,
  IconPlus,
  IconSearch,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import { Switch } from '@/components/ui/switch'
import { SipExtensionFormDialog } from '@/app/components/features/call-center/sip-extension-form-dialog'
import { SipRegistrationSecretDialog } from '@/app/components/features/call-center/sip-registration-secret-dialog'
import {
  useDisableSipExtension,
  useEnableSipExtension,
  useResetSipExtensionPassword,
  useSipExtensions,
} from '@/service/use-sip-extensions'
import { get } from '@/service/base'
import type {
  SipExtension,
  SipRegistrationSecret,
} from '@/models/sip-extension'

const PER_PAGE = 20

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

function formatDateTime(value: string | null, locale: 'zh' | 'en'): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

export default function SipExtensionsPage() {
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [registrationStatus, setRegistrationStatus] = useState<'' | 'registered' | 'unregistered'>('')
  const [activeStatus, setActiveStatus] = useState<'' | 'active' | 'inactive'>('')

  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<SipExtension | null>(null)
  const [secret, setSecret] = useState<SipRegistrationSecret | null>(null)
  const [resetTarget, setResetTarget] = useState<SipExtension | null>(null)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data, isLoading, isError, refetch } = useSipExtensions({
    page,
    per_page: PER_PAGE,
    keyword: keyword || undefined,
    registration_status: registrationStatus || undefined,
    active_status: activeStatus || undefined,
  })

  const disableMutation = useDisableSipExtension()
  const enableMutation = useEnableSipExtension()
  const resetMutation = useResetSipExtensionPassword()

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setKeyword(searchInput.trim())
      setPage(1)
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [searchInput])

  const openCreate = () => {
    setEditTarget(null)
    setFormOpen(true)
  }

  const openEdit = (item: SipExtension) => {
    setEditTarget(item)
    setFormOpen(true)
  }

  const handleToggleActive = useCallback(
    async (item: SipExtension) => {
      try {
        if (item.is_active) {
          await disableMutation.mutateAsync(item.id)
          toast.success(t('se.toast.disabled', locale))
        } else {
          await enableMutation.mutateAsync(item.id)
          toast.success(t('se.toast.enabled', locale))
        }
      } catch (error) {
        const message = await readErrorMessage(error, t('se.toast.operationFailed', locale))
        toast.error(message)
      }
    },
    [disableMutation, enableMutation, locale],
  )

  const handleCopyRegistrationInfo = useCallback(
    async (item: SipExtension) => {
      try {
        const info = await get<SipRegistrationSecret>(`v1/sip-extensions/${item.id}/registration-info`)
        const text = [
          `${t('se.reg.server', locale)}: ${info.registration_server ?? ''}`,
          `${t('se.reg.port', locale)}: ${info.registration_port ?? ''}`,
          `${t('se.reg.transport', locale)}: ${info.transport ?? ''}`,
          `${t('se.reg.userId', locale)}: ${info.sip_user_id}`,
          `${t('se.reg.authAccount', locale)}: ${info.auth_account}`,
          `${t('se.reg.authPassword', locale)}: ${info.auth_password_masked}`,
        ].join('\n')
        const ok = await copyPlainTextToClipboard(text)
        if (ok) toast.success(t('se.copy.success', locale))
        else toast.error(t('se.copy.failed', locale))
      } catch (error) {
        const message = await readErrorMessage(error, t('se.toast.operationFailed', locale))
        toast.error(message)
      }
    },
    [locale],
  )

  const handleResetPassword = useCallback(async () => {
    if (!resetTarget) return
    try {
      const response = await resetMutation.mutateAsync(resetTarget.id)
      setResetTarget(null)
      setSecret(response.registration_info)
    } catch (error) {
      const message = await readErrorMessage(error, t('se.toast.operationFailed', locale))
      toast.error(message)
      setResetTarget(null)
    }
  }, [resetTarget, resetMutation, locale])

  const hasFilter = keyword.length > 0 || registrationStatus !== '' || activeStatus !== ''

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t('se.title', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('se.description', locale)}</p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/85"
        >
          <IconPlus size={18} />
          {t('se.new', locale)}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] max-w-md flex-1">
          <IconSearch
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder={t('se.search.placeholder', locale)}
            className="h-9 w-full rounded-lg border border-border bg-white pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            aria-label={t('se.search.placeholder', locale)}
          />
        </div>
        <select
          value={registrationStatus}
          onChange={(event) => {
            setRegistrationStatus(event.target.value as typeof registrationStatus)
            setPage(1)
          }}
          className="h-9 rounded-lg border border-border bg-white px-3 text-sm text-foreground"
          aria-label={t('se.filter.registration', locale)}
        >
          <option value="">{t('se.filter.registration.all', locale)}</option>
          <option value="registered">{t('se.status.registered', locale)}</option>
          <option value="unregistered">{t('se.status.unregistered', locale)}</option>
        </select>
        <select
          value={activeStatus}
          onChange={(event) => {
            setActiveStatus(event.target.value as typeof activeStatus)
            setPage(1)
          }}
          className="h-9 rounded-lg border border-border bg-white px-3 text-sm text-foreground"
          aria-label={t('se.filter.active', locale)}
        >
          <option value="">{t('se.filter.active.all', locale)}</option>
          <option value="active">{t('se.status.active', locale)}</option>
          <option value="inactive">{t('se.status.inactive', locale)}</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('se.loading', locale)}</p>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <p className="text-sm text-muted-foreground">{t('se.loadFailed', locale)}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('se.retry', locale)}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            <IconDeviceLandlinePhone size={22} />
          </div>
          <p className="text-sm text-muted-foreground">
            {hasFilter ? t('se.emptySearch', locale) : t('se.empty', locale)}
          </p>
          {!hasFilter && (
            <button
              type="button"
              onClick={openCreate}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
            >
              <IconPlus size={18} />
              {t('se.new', locale)}
            </button>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="flex h-12 items-center gap-4 bg-muted px-6 text-sm font-semibold text-foreground/80">
            <div className="w-28">{t('se.col.number', locale)}</div>
            <div className="flex-1">{t('se.col.name', locale)}</div>
            <div className="w-24">{t('se.col.registration', locale)}</div>
            <div className="min-w-0 flex-[1.2]">{t('se.col.employee', locale)}</div>
            <div className="w-36">{t('se.col.occupant', locale)}</div>
            <div className="w-20">{t('se.col.active', locale)}</div>
            <div className="w-40">{t('se.col.lastRegistered', locale)}</div>
            <div className="w-28 text-right">{t('se.col.actions', locale)}</div>
          </div>
          {items.map((item) => (
            <ExtensionRow
              key={item.id}
              item={item}
              locale={locale}
              onEdit={() => openEdit(item)}
              onCopyInfo={() => handleCopyRegistrationInfo(item)}
              onReset={() => setResetTarget(item)}
              onToggleActive={() => handleToggleActive(item)}
            />
          ))}
        </div>
      )}

      {!isLoading && !isError && total > 0 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{t('se.pagination.total', locale, { total: String(total) })}</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="h-9 rounded-lg border border-border px-3 disabled:opacity-50"
            >
              {t('se.pagination.prev', locale)}
            </button>
            <span>
              {page} / {Math.max(pages, 1)}
            </span>
            <button
              type="button"
              disabled={pages === 0 || page >= pages}
              onClick={() => setPage((current) => current + 1)}
              className="h-9 rounded-lg border border-border px-3 disabled:opacity-50"
            >
              {t('se.pagination.next', locale)}
            </button>
          </div>
        </div>
      )}

      <SipExtensionFormDialog
        open={formOpen}
        target={editTarget}
        onClose={() => setFormOpen(false)}
        onCreated={(response) => {
          setFormOpen(false)
          setSecret(response.registration_info)
        }}
      />

      <SipRegistrationSecretDialog secret={secret} onDone={() => setSecret(null)} />

      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-[440px] max-w-[90vw] rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                <IconKey size={20} />
              </div>
              <h2 className="text-base font-semibold text-foreground">{t('se.reset.title', locale)}</h2>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">
              {t('se.reset.confirm', locale, { number: resetTarget.extension_number })}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setResetTarget(null)}
                disabled={resetMutation.isPending}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
              >
                {t('se.cancel', locale)}
              </button>
              <button
                type="button"
                onClick={handleResetPassword}
                disabled={resetMutation.isPending}
                className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/85 disabled:opacity-50"
              >
                {resetMutation.isPending ? '...' : t('se.reset.submit', locale)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ExtensionRow({
  item,
  locale,
  onEdit,
  onCopyInfo,
  onReset,
  onToggleActive,
}: {
  item: SipExtension
  locale: 'zh' | 'en'
  onEdit: () => void
  onCopyInfo: () => void
  onReset: () => void
  onToggleActive: () => void
}) {
  const registered = item.registration_status === 'registered' && item.is_active
  return (
    <div className="flex min-h-14 items-center gap-4 border-t border-border px-6 py-3 text-sm text-foreground">
      <div className="w-28 font-mono font-medium">{item.extension_number}</div>
      <div className="min-w-0 flex-1 truncate">{item.name}</div>
      <div className="w-24">
        <span
          className={cn(
            'inline-block rounded-md px-2 py-1 text-xs font-medium',
            registered ? 'bg-green-50 text-green-700' : 'bg-muted text-muted-foreground',
          )}
          title={
            registered
              ? `${t('se.status.registered', locale)} · ${formatDateTime(item.last_registered_at, locale)}`
              : undefined
          }
        >
          {registered ? t('se.status.registered', locale) : t('se.status.unregistered', locale)}
        </span>
      </div>
      <div
        className="min-w-0 flex-[1.2] truncate"
        title={(item.bound_employees ?? []).map((person) => person.name).join('、') || undefined}
      >
        {(item.bound_employees?.length ?? 0) === 0 ? (
          <span className="text-muted-foreground">{t('se.employee.unbound', locale)}</span>
        ) : (item.bound_employees?.length ?? 0) <= 3 ? (
          <span>{item.bound_employees.map((person) => person.name).join('、')}</span>
        ) : (
          <span>
            {item.bound_employees
              .slice(0, 3)
              .map((person) => person.name)
              .join('、')}
            {t('se.employee.more', locale, {
              count: String(item.bound_employees.length),
            })}
          </span>
        )}
      </div>
      <div className="w-36 truncate" title={item.current_occupant?.name || undefined}>
        {item.current_occupant?.name || (
          <span className="text-muted-foreground">{t('se.occupant.none', locale)}</span>
        )}
      </div>
      <div className="w-20">
        <Switch
          checked={item.is_active}
          onCheckedChange={onToggleActive}
          aria-label={item.is_active ? t('se.action.disable', locale) : t('se.action.enable', locale)}
        />
      </div>
      <div className="w-40 text-muted-foreground">{formatDateTime(item.last_registered_at, locale)}</div>
      <div className="flex w-28 items-center justify-end gap-3">
        <button
          type="button"
          onClick={onEdit}
          className="text-foreground/80 transition-colors hover:text-foreground"
          title={t('se.action.edit', locale)}
          aria-label={t('se.action.edit', locale)}
        >
          <IconPencil size={17} />
        </button>
        <button
          type="button"
          onClick={onCopyInfo}
          className="text-foreground/80 transition-colors hover:text-foreground"
          title={t('se.action.copyInfo', locale)}
          aria-label={t('se.action.copyInfo', locale)}
        >
          <IconCopy size={17} />
        </button>
        <button
          type="button"
          onClick={onReset}
          className="text-foreground/80 transition-colors hover:text-foreground"
          title={t('se.action.reset', locale)}
          aria-label={t('se.action.reset', locale)}
        >
          <IconKey size={17} />
        </button>
      </div>
    </div>
  )
}
