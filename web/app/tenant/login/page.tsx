'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { isConsoleHttpStatus, saveConsoleToken } from '@/service/tenant-console-client'
import { useConsoleLogin } from '@/service/use-tenant-console'
import { FIELD_CLASS, Field } from '@/app/tenant/_components/console-ui'

export default function TenantConsoleLoginPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const login = useConsoleLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) {
      setError(t('tc.login.required', locale))
      return
    }
    setError('')
    try {
      const res = await login.mutateAsync({ username: username.trim(), password })
      saveConsoleToken(res.access_token)
      router.replace('/tenant')
    } catch (err) {
      if (isConsoleHttpStatus(err, 401)) setError(t('tc.login.invalid', locale))
      else if (isConsoleHttpStatus(err, 429)) setError(t('tc.login.locked', locale))
      else if (isConsoleHttpStatus(err, 503)) setError(t('tc.login.disabled', locale))
      else setError(t('tc.login.failed', locale))
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-xl border border-border bg-background p-8 shadow-sm"
      >
        <div>
          <h1 className="font-display text-xl font-bold text-foreground">{t('tc.brand', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('tc.login.subtitle', locale)}</p>
        </div>
        <Field label={t('tc.login.username', locale)} htmlFor="tc-username">
          <input
            id="tc-username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field label={t('tc.login.password', locale)} htmlFor="tc-password">
          <input
            id="tc-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={login.isPending}>
          {login.isPending ? t('tc.login.submitting', locale) : t('tc.login.submit', locale)}
        </Button>
      </form>
    </div>
  )
}
