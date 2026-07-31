'use client'

import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconHeadset, IconEye, IconEyeOff } from '@tabler/icons-react'
import { useLogin, useSsoLogin } from '@/service/use-auth'
import { useSystemInfo } from '@/service/use-system'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { getDefaultAccessiblePath } from '@/utils/permissions'
import { loginSchema, TENANT_IDENTIFIER_REGEX } from '@/utils/validators'
import { cn } from '@/lib/utils'
import { LegalFooter } from '@/components/legal-footer'
import { SESSION_REPLACED_REASON } from '@/utils/session-replacement'

const LAST_TENANT_KEY = 'opendesk_last_tenant'
// Survive AuthSessionKeeper reloads that strip ?sso_token= from the address bar.
const SSO_PENDING_TOKEN_KEY = 'opendesk_pending_sso_token'
const SSO_PENDING_REDIRECT_KEY = 'opendesk_pending_sso_redirect'
// Set when SSO finishes so a mid-navigation reload still enters the app.
const SSO_NAV_KEY = 'opendesk_sso_nav'
// Module-level so Suspense remounts of LoginPage do not re-exchange the same token.
const handledSsoTokens = new Set<string>()

function clearPendingSso() {
  try {
    sessionStorage.removeItem(SSO_PENDING_TOKEN_KEY)
    sessionStorage.removeItem(SSO_PENDING_REDIRECT_KEY)
  } catch {
    // sessionStorage unavailable
  }
}

function readPendingSso(): { token: string | null; redirect: string | null } {
  try {
    return {
      token: sessionStorage.getItem(SSO_PENDING_TOKEN_KEY),
      redirect: sessionStorage.getItem(SSO_PENDING_REDIRECT_KEY),
    }
  } catch {
    return { token: null, redirect: null }
  }
}

function writePendingSso(token: string, redirect: string | null) {
  try {
    sessionStorage.setItem(SSO_PENDING_TOKEN_KEY, token)
    if (redirect && redirect.startsWith('/')) {
      sessionStorage.setItem(SSO_PENDING_REDIRECT_KEY, redirect)
    } else {
      sessionStorage.removeItem(SSO_PENDING_REDIRECT_KEY)
    }
  } catch {
    // sessionStorage unavailable
  }
}

function markSsoNavigation(path: string) {
  try {
    sessionStorage.setItem(SSO_NAV_KEY, path)
  } catch {
    // sessionStorage unavailable
  }
}

function consumeSsoNavigation(): string | null {
  try {
    const path = sessionStorage.getItem(SSO_NAV_KEY)
    if (!path) return null
    sessionStorage.removeItem(SSO_NAV_KEY)
    return path.startsWith('/') ? path : null
  } catch {
    return null
  }
}

export default function LoginPageWrapper() {
  return (
    <Suspense>
      <LoginPage />
    </Suspense>
  )
}

function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { setAuth, token, user } = useAuthStore()
  const { locale, setLocale } = useLocaleStore()
  const loginMutation = useLogin()
  const ssoLoginMutation = useSsoLogin()
  const { data: systemInfo } = useSystemInfo()
  // Default to false (= show field) when info unavailable — safer for users
  // who otherwise wouldn't see what to type.
  const singleTenantMode = systemInfo?.single_tenant_mode ?? false

  const [formData, setFormData] = useState({ tenant: '', username: '', password: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showSessionReplacedAlert, setShowSessionReplacedAlert] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    setShowSessionReplacedAlert(searchParams.get('reason') === SESSION_REPLACED_REASON)
  }, [searchParams])

  // SSO finished but a cross-tab reload interrupted router.replace — resume entry.
  // Do not auto-bounce every logged-in visit to /login (password account switch).
  useEffect(() => {
    if (!mounted || !token || !user) return
    if (searchParams.get('reason') === SESSION_REPLACED_REASON) return
    if (searchParams.get('sso_token') || readPendingSso().token) return
    const path = consumeSsoNavigation()
    if (!path) return
    router.replace(path)
  }, [mounted, token, user, router, searchParams])

  useEffect(() => {
    const fromQuery = searchParams.get('sso_token')
    const pending = readPendingSso()
    const ssoToken = fromQuery || pending.token
    if (!ssoToken || handledSsoTokens.has(ssoToken)) return
    handledSsoTokens.add(ssoToken)

    // Capture before stripping the query; useSearchParams may update after replaceState.
    const redirect =
      (fromQuery ? searchParams.get('redirect') : null) || pending.redirect

    // Persist across reloads, then drop sso_token from the URL so a later
    // reload cannot keep replaying a bearer credential from the address bar.
    writePendingSso(ssoToken, redirect)
    if (fromQuery) {
      const url = new URL(window.location.href)
      url.searchParams.delete('sso_token')
      const next = `${url.pathname}${url.search}${url.hash}`
      window.history.replaceState(window.history.state, '', next)
    }

    setApiError('')
    ssoLoginMutation.mutate(ssoToken, {
      onSuccess: (data) => {
        const defaultPath = getDefaultAccessiblePath(data.user)
        const path = redirect && redirect.startsWith('/') ? redirect : defaultPath
        setAuth(data.user, data.access_token)
        markSsoNavigation(path)
        clearPendingSso()
        router.replace(path)
      },
      onError: async (err: unknown) => {
        clearPendingSso()
        let status = 0
        let code = ''
        let message = ''
        if (err && typeof err === 'object' && 'response' in err) {
          const response = (err as { response: Response }).response
          status = response.status
          try {
            const body = await response.json()
            code = body?.code ?? ''
            message = typeof body?.message === 'string' ? body.message : ''
          } catch {
            // ignore json parse error
          }
        }
        // First attempt may have already claimed jti and written localStorage
        // before this tab was reloaded — land on that session instead of /login.
        if (message.toLowerCase().includes('already used')) {
          const current = useAuthStore.getState()
          if (current.token && current.user) {
            const defaultPath = getDefaultAccessiblePath(current.user)
            const path = redirect && redirect.startsWith('/') ? redirect : defaultPath
            markSsoNavigation(path)
            router.replace(path)
            return
          }
        }
        setApiError(mapApiError(status, code))
      },
    })
  }, [router, searchParams, setAuth, ssoLoginMutation])

  useEffect(() => {
    if (singleTenantMode && systemInfo) {
      setFormData((prev) => ({ ...prev, tenant: systemInfo.default_tenant_id }))
      return
    }
    const tenantParam = searchParams.get('tenant')
    if (tenantParam && TENANT_IDENTIFIER_REGEX.test(tenantParam)) {
      setFormData((prev) => ({ ...prev, tenant: tenantParam }))
    } else {
      try {
        const saved = localStorage.getItem(LAST_TENANT_KEY)
        if (saved && TENANT_IDENTIFIER_REGEX.test(saved)) {
          setFormData((prev) => ({ ...prev, tenant: saved }))
        } else if (saved) {
          localStorage.removeItem(LAST_TENANT_KEY)
        }
      } catch {
        // localStorage unavailable
      }
    }
  }, [searchParams, singleTenantMode, systemInfo])

  const validateField = useCallback(
    (field: string, value: string) => {
      const partial = { ...formData, [field]: value }
      const result = loginSchema.safeParse(partial)
      if (result.success) {
        setFieldErrors((prev) => {
          const next = { ...prev }
          delete next[field]
          return next
        })
      } else {
        const issue = result.error.issues.find((i) => i.path[0] === field)
        if (issue) {
          setFieldErrors((prev) => ({ ...prev, [field]: t(issue.message, locale) }))
        }
      }
    },
    [formData, locale]
  )

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    validateField(field, formData[field as keyof typeof formData])
  }

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
    setApiError('')
    setShowSessionReplacedAlert(false)
    if (touched[field]) {
      validateField(field, value)
    }
  }

  const mapApiError = (status: number, code?: string): string => {
    if (code === 'NOT_FOUND') return t('error.tenant_not_found', locale)
    if (code === 'UNAUTHORIZED') {
      return t('error.invalid_credentials', locale)
    }
    if (status === 0 || status >= 500) return t('error.network', locale)
    return t('error.invalid_credentials', locale)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setApiError('')

    const result = loginSchema.safeParse(formData)
    if (!result.success) {
      const errors: Record<string, string> = {}
      result.error.issues.forEach((issue) => {
        const field = issue.path[0] as string
        if (!errors[field]) {
          errors[field] = t(issue.message, locale)
        }
      })
      setFieldErrors(errors)
      setTouched({ tenant: true, username: true, password: true })
      return
    }

    try {
      const data = await loginMutation.mutateAsync(result.data)
      if (!singleTenantMode) {
        try {
          localStorage.setItem(LAST_TENANT_KEY, result.data.tenant)
        } catch {
          // localStorage unavailable
        }
      }
      setAuth(data.user, data.access_token)
      const redirect = searchParams.get('redirect')
      const defaultPath = getDefaultAccessiblePath(data.user)
      router.replace(redirect && redirect.startsWith('/') ? redirect : defaultPath)
    } catch (err: unknown) {
      let status = 0
      let code = ''
      if (err && typeof err === 'object' && 'response' in err) {
        const response = (err as { response: Response }).response
        status = response.status
        try {
          const body = await response.json()
          code = body?.code ?? ''
          if (code === 'UNAUTHORIZED' && body?.message?.toLowerCase().includes('disabled')) {
            setApiError(t('error.account_disabled', locale))
            return
          }
        } catch {
          // ignore json parse error
        }
      }
      setApiError(mapApiError(status, code))
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-muted">
      {/* Header bar */}
      <div className="flex h-14 items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <IconHeadset size={28} className="text-foreground" />
          <span className="font-sans text-xl font-semibold text-foreground">OpenDesk</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setLocale('zh')}
            className={cn(
              'rounded-md px-3 py-2 text-sm font-medium transition-colors',
              locale === 'zh'
                ? 'bg-border text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            中文
          </button>
          <button
            type="button"
            onClick={() => setLocale('en')}
            className={cn(
              'rounded-md px-3 py-2 text-sm transition-colors',
              locale === 'en'
                ? 'bg-border font-medium text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            English
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-1 items-center justify-center">
        <div className="w-[400px] rounded-xl border border-border bg-white p-6">
          {showSessionReplacedAlert && (
            <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3">
              <p className="text-[13px] text-destructive/80">
                {t('login.session_replaced', locale)}
              </p>
            </div>
          )}

          {/* Title */}
          <div className="mb-3 flex flex-col gap-2">
            <h1 className="font-sans text-2xl font-bold text-foreground">
              {t('login.title', locale)}
            </h1>
            <p className="text-sm text-muted-foreground">{t('login.subtitle', locale)}</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            {/* Tenant — hidden in single-tenant mode (OSS edition); the value
                is auto-filled from /api/v1/system/info default_tenant_id. */}
            {!singleTenantMode && (
              <div>
                <label
                  htmlFor="login-tenant"
                  className="mb-1 block text-sm font-medium text-foreground"
                >
                  {t('login.tenant', locale)}
                </label>
                <input
                  id="login-tenant"
                  name="tenant"
                  type="text"
                  autoComplete="organization"
                  value={formData.tenant}
                  onChange={(e) => handleChange('tenant', e.target.value)}
                  onBlur={() => handleBlur('tenant')}
                  placeholder={t('login.tenant.placeholder', locale)}
                  className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                />
                {touched.tenant && fieldErrors.tenant && (
                  <p className="mt-1 text-xs text-destructive/80">{fieldErrors.tenant}</p>
                )}
              </div>
            )}

            {/* Username */}
            <div>
              <label
                htmlFor="login-username"
                className="mb-1 block text-sm font-medium text-foreground"
              >
                {t('login.username', locale)}
              </label>
              <input
                id="login-username"
                name="username"
                type="text"
                autoComplete="username"
                value={formData.username}
                onChange={(e) => handleChange('username', e.target.value)}
                onBlur={() => handleBlur('username')}
                placeholder={t('login.username.placeholder', locale)}
                className="h-10 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
              />
              {touched.username && fieldErrors.username && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.username}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="login-password"
                className="mb-1 block text-sm font-medium text-foreground"
              >
                {t('login.password', locale)}
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={formData.password}
                  onChange={(e) => handleChange('password', e.target.value)}
                  onBlur={() => handleBlur('password')}
                  placeholder={t('login.password.placeholder', locale)}
                  className="h-10 w-full rounded-lg border border-border bg-white px-3 pr-10 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                </button>
              </div>
              {touched.password && fieldErrors.password && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.password}</p>
              )}
            </div>

            {/* Error alert */}
            {apiError && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3">
                <p className="text-[13px] text-destructive/80">{apiError}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="flex h-10 w-full items-center justify-center rounded-lg bg-foreground text-sm font-semibold text-white transition-colors hover:bg-foreground/90 disabled:opacity-60"
            >
              {loginMutation.isPending ? t('login.loading', locale) : t('login.submit', locale)}
            </button>

            {/* Forgot password */}
            <div className="flex justify-end">
              <a
                href={`/login/forgot-password${
                  formData.tenant ? `?tenant=${encodeURIComponent(formData.tenant)}` : ''
                }`}
                className="text-sm text-primary hover:underline"
              >
                {t('login.forgot', locale)}
              </a>
            </div>
          </form>
        </div>
      </div>

      {/* AGPL §13 notice — network users must be offered the corresponding source. */}
      <LegalFooter />
    </div>
  )
}
