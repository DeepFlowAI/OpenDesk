'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  IconBan,
  IconCircleCheck,
  IconCopy,
  IconKey,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useApiKeys,
  useCreateApiKey,
  useDeleteApiKey,
  useDisableApiKey,
  useEnableApiKey,
  useRotateApiKey,
} from '@/service/use-api-keys'
import type { ApiKeyRecord, ApiKeySecretResponse } from '@/models/api-key'
import { cn } from '@/lib/utils'

type ConfirmAction = 'disable' | 'enable' | 'rotate' | 'delete'
type ConfirmTarget = { action: ConfirmAction; item: ApiKeyRecord }

function formatDate(value: string | null, locale: 'zh' | 'en') {
  if (!value) return '-'
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

function CreateDialog({
  open,
  existingNames,
  loading,
  onCancel,
  onSubmit,
}: {
  open: boolean
  existingNames: string[]
  loading: boolean
  onCancel: () => void
  onSubmit: (name: string) => void
}) {
  const { locale } = useLocaleStore()
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const duplicateName = existingNames.includes(name.trim())

  useEffect(() => {
    if (!open) {
      setName('')
      setError('')
    }
  }, [open])

  if (!open) return null

  const submit = () => {
    const nextName = name.trim()
    if (nextName.length < 2 || nextName.length > 40) {
      setError(t('apiKeys.validation.name', locale))
      return
    }
    onSubmit(nextName)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[440px] max-w-[90vw] rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-foreground">{t('apiKeys.create.title', locale)}</h2>
        <div className="mt-5 flex flex-col gap-2">
          <label className="text-sm font-medium text-foreground">{t('apiKeys.form.name', locale)}</label>
          <input
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setError('')
            }}
            maxLength={40}
            className="h-10 rounded-lg border border-border bg-white px-3 text-sm outline-none transition-colors focus:border-foreground/40"
            placeholder={t('apiKeys.form.name.placeholder', locale)}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
          {duplicateName && !error && (
            <p className="text-xs text-muted-foreground">{t('apiKeys.form.name.duplicate', locale)}</p>
          )}
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
          >
            {t('apiKeys.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={loading}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:opacity-50"
          >
            {loading ? '...' : t('apiKeys.create.submit', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

function SecretDialog({
  secret,
  onDone,
  onCopy,
}: {
  secret: ApiKeySecretResponse | null
  onDone: () => void
  onCopy: (value: string) => void
}) {
  const { locale } = useLocaleStore()
  const [confirmed, setConfirmed] = useState(false)

  if (!secret) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[560px] max-w-[92vw] rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
            <IconKey size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{t('apiKeys.secret.title', locale)}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('apiKeys.secret.description', locale)}</p>
          </div>
        </div>
        <div className="mt-5 rounded-lg border border-border bg-muted/50 p-3">
          <div className="flex items-center gap-3">
            <code className="flex-1 break-all font-mono text-sm text-foreground">{secret.api_key}</code>
            <button
              type="button"
              onClick={() => onCopy(secret.api_key)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-white text-foreground/80 transition-colors hover:text-foreground"
              title={t('apiKeys.copy', locale)}
            >
              <IconCopy size={18} />
            </button>
          </div>
        </div>
        <label className="mt-5 flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          {t('apiKeys.secret.saved', locale)}
        </label>
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={() => {
              setConfirmed(false)
              onDone()
            }}
            disabled={!confirmed}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:opacity-50"
          >
            {t('apiKeys.done', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

function ConfirmDialog({
  target,
  loading,
  onCancel,
  onConfirm,
}: {
  target: ConfirmTarget | null
  loading: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  if (!target) return null

  const destructive = target.action === 'delete'
  const title = t(`apiKeys.confirm.${target.action}.title`, locale)
  const message = t(`apiKeys.confirm.${target.action}.message`, locale)
  const confirmLabel = t(`apiKeys.confirm.${target.action}.ok`, locale)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[440px] max-w-[90vw] rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        <p className="mt-3 text-sm text-muted-foreground">{message}</p>
        <div className="mt-3 rounded-lg border border-border p-3">
          <p className="truncate text-sm font-medium text-foreground">{target.item.name}</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{target.item.masked_key}</p>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
          >
            {t('apiKeys.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={cn(
              'h-9 rounded-lg px-4 text-sm font-medium text-white transition-colors disabled:opacity-50',
              destructive ? 'bg-destructive hover:bg-destructive/85' : 'bg-primary hover:bg-primary/85'
            )}
          >
            {loading ? '...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function ApiKeyManager() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useApiKeys()
  const createMutation = useCreateApiKey()
  const disableMutation = useDisableApiKey()
  const enableMutation = useEnableApiKey()
  const rotateMutation = useRotateApiKey()
  const deleteMutation = useDeleteApiKey()

  const [createOpen, setCreateOpen] = useState(false)
  const [secret, setSecret] = useState<ApiKeySecretResponse | null>(null)
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null)

  const items = data ?? []
  const existingNames = useMemo(() => items.map((item) => item.name), [items])
  const confirming = disableMutation.isPending || enableMutation.isPending || rotateMutation.isPending || deleteMutation.isPending

  const handleCreate = async (name: string) => {
    try {
      const response = await createMutation.mutateAsync({ name })
      setCreateOpen(false)
      setSecret(response)
    } catch {
      toast.error(t('apiKeys.create.failed', locale))
    }
  }

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      toast.success(t('apiKeys.copy.success', locale))
    } catch {
      toast.error(t('apiKeys.copy.failed', locale))
    }
  }

  const handleConfirm = async () => {
    if (!confirmTarget) return
    try {
      if (confirmTarget.action === 'disable') {
        await disableMutation.mutateAsync(confirmTarget.item.id)
        toast.success(t('apiKeys.disable.success', locale))
      }
      if (confirmTarget.action === 'enable') {
        await enableMutation.mutateAsync(confirmTarget.item.id)
        toast.success(t('apiKeys.enable.success', locale))
      }
      if (confirmTarget.action === 'delete') {
        await deleteMutation.mutateAsync(confirmTarget.item.id)
        toast.success(t('apiKeys.delete.success', locale))
      }
      if (confirmTarget.action === 'rotate') {
        const response = await rotateMutation.mutateAsync(confirmTarget.item.id)
        setSecret(response)
      }
      setConfirmTarget(null)
    } catch {
      toast.error(t('apiKeys.operation.failed', locale))
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t('apiKeys.title', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('apiKeys.description', locale)}</p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/85"
        >
          <IconPlus size={18} />
          {t('apiKeys.new', locale)}
        </button>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">{t('apiKeys.loading', locale)}</div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            <IconKey size={22} />
          </div>
          <p className="text-sm text-muted-foreground">{t('apiKeys.empty', locale)}</p>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white"
          >
            <IconPlus size={18} />
            {t('apiKeys.new', locale)}
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
            <div className="flex min-w-0 flex-1 items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('apiKeys.col.name', locale)}</span>
            </div>
            <div className="flex w-[220px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('apiKeys.col.key', locale)}</span>
            </div>
            <div className="flex w-[110px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('apiKeys.col.status', locale)}</span>
            </div>
            <div className="flex w-[180px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('apiKeys.col.createdAt', locale)}</span>
            </div>
            <div className="flex w-[120px] items-center">
              <span className="text-sm font-semibold text-foreground/80">{t('apiKeys.col.actions', locale)}</span>
            </div>
          </div>
          {items.map((item) => (
            <div key={item.id} className="flex h-14 items-center gap-6 border-t border-border px-6">
              <div className="flex min-w-0 flex-1 items-center">
                <span className="truncate text-sm text-foreground">{item.name}</span>
              </div>
              <div className="flex w-[220px] items-center">
                <span className="font-mono text-sm text-muted-foreground">{item.masked_key}</span>
              </div>
              <div className="flex w-[110px] items-center">
                <span
                  className={cn(
                    'rounded-md px-2 py-1 text-xs font-medium',
                    item.is_active ? 'bg-green-50 text-green-700' : 'bg-muted text-muted-foreground'
                  )}
                >
                  {item.is_active ? t('apiKeys.status.active', locale) : t('apiKeys.status.disabled', locale)}
                </span>
              </div>
              <div className="flex w-[180px] items-center">
                <span className="text-sm text-muted-foreground">{formatDate(item.created_at, locale)}</span>
              </div>
              <div className="flex w-[120px] items-center gap-3">
                {item.is_active ? (
                  <button
                    type="button"
                    onClick={() => setConfirmTarget({ action: 'disable', item })}
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    title={t('apiKeys.action.disable', locale)}
                  >
                    <IconBan size={18} />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmTarget({ action: 'enable', item })}
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    title={t('apiKeys.action.enable', locale)}
                  >
                    <IconCircleCheck size={18} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setConfirmTarget({ action: 'rotate', item })}
                  className="text-foreground/80 transition-colors hover:text-foreground"
                  title={t('apiKeys.action.rotate', locale)}
                >
                  <IconRefresh size={18} />
                </button>
                {!item.is_active && (
                  <button
                    type="button"
                    onClick={() => setConfirmTarget({ action: 'delete', item })}
                    className="text-foreground/80 transition-colors hover:text-destructive"
                    title={t('apiKeys.action.delete', locale)}
                  >
                    <IconTrash size={18} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateDialog
        open={createOpen}
        existingNames={existingNames}
        loading={createMutation.isPending}
        onCancel={() => {
          setCreateOpen(false)
        }}
        onSubmit={handleCreate}
      />
      <SecretDialog secret={secret} onDone={() => setSecret(null)} onCopy={handleCopy} />
      <ConfirmDialog
        target={confirmTarget}
        loading={confirming}
        onCancel={() => setConfirmTarget(null)}
        onConfirm={handleConfirm}
      />
    </div>
  )
}
