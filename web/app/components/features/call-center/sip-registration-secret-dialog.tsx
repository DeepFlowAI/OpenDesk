'use client'

import { useMemo, useState } from 'react'
import { IconCopy, IconKey } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import type { SipRegistrationSecret } from '@/models/sip-extension'

type SecretRow = { labelKey: string; value: string | null; phoneFieldKey?: string }

/**
 * Shows the full SIP registration info (including the plaintext password)
 * after creating an extension or resetting its password. Values
 * that the deployment did not provide are rendered blank rather than filled
 * with a default.
 */
export function SipRegistrationSecretDialog({
  secret,
  onDone,
}: {
  secret: SipRegistrationSecret | null
  onDone: () => void
}) {
  const { locale } = useLocaleStore()
  const [confirmed, setConfirmed] = useState(false)

  const rows: SecretRow[] = useMemo(
    () =>
      secret
        ? [
            { labelKey: 'se.reg.server', value: secret.registration_server, phoneFieldKey: 'se.reg.field.server' },
            { labelKey: 'se.reg.port', value: secret.registration_port, phoneFieldKey: 'se.reg.field.port' },
            { labelKey: 'se.reg.transport', value: secret.transport, phoneFieldKey: 'se.reg.field.transport' },
            { labelKey: 'se.reg.userId', value: secret.sip_user_id, phoneFieldKey: 'se.reg.field.userId' },
            { labelKey: 'se.reg.authAccount', value: secret.auth_account, phoneFieldKey: 'se.reg.field.authAccount' },
            { labelKey: 'se.reg.authPassword', value: secret.auth_password, phoneFieldKey: 'se.reg.field.authPassword' },
          ]
        : [],
    [secret],
  )

  if (!secret) return null

  const copy = async (value: string | null) => {
    if (!value) return
    const ok = await copyPlainTextToClipboard(value)
    if (ok) toast.success(t('se.copy.success', locale))
    else toast.error(t('se.copy.failed', locale))
  }

  const copyAll = async () => {
    const text = rows
      .map((row) => `${t(row.labelKey, locale)}: ${row.value ?? ''}`)
      .join('\n')
    const ok = await copyPlainTextToClipboard(text)
    if (ok) toast.success(t('se.copy.success', locale))
    else toast.error(t('se.copy.failed', locale))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[560px] max-w-[92vw] rounded-xl bg-white p-6 shadow-xl">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
            <IconKey size={20} />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">{t('se.secret.title', locale)}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t('se.secret.description', locale)}</p>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-2">
          {rows.map((row) => (
            <div
              key={row.labelKey}
              className="flex items-center gap-3 rounded-lg border border-border bg-muted/50 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">
                  {t(row.labelKey, locale)}
                  {row.phoneFieldKey ? (
                    <span className="ml-1 text-muted-foreground/70">· {t(row.phoneFieldKey, locale)}</span>
                  ) : null}
                </p>
                <p className="break-all font-mono text-sm text-foreground">{row.value || '—'}</p>
              </div>
              <button
                type="button"
                onClick={() => copy(row.value)}
                disabled={!row.value}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-white text-foreground/80 transition-colors hover:text-foreground disabled:opacity-40"
                title={t('se.copy', locale)}
                aria-label={t('se.copy', locale)}
              >
                <IconCopy size={16} />
              </button>
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-amber-600">{t('se.secret.warning', locale)}</p>
          <button
            type="button"
            onClick={copyAll}
            className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconCopy size={15} />
            {t('se.copyAll', locale)}
          </button>
        </div>

        <label className="mt-5 flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          {t('se.secret.saved', locale)}
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
            {t('se.done', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}
