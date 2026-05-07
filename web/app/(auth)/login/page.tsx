'use client'

import { useState, useEffect, useCallback, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconHeadset, IconEye, IconEyeOff } from '@tabler/icons-react'
import { useLogin } from '@/service/use-auth'
import { useSystemInfo } from '@/service/use-system'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { loginSchema } from '@/utils/validators'
import { cn } from '@/lib/utils'
import { LegalFooter } from '@/components/legal-footer'

const TENANT_REGEX = /^[a-zA-Z0-9-]{2,32}$/
const LAST_TENANT_KEY = 'opendesk_last_tenant'

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
  const { setAuth } = useAuthStore()
  const { locale, setLocale } = useLocaleStore()
  const loginMutation = useLogin()
  const { data: systemInfo } = useSystemInfo()
  // Default to false (= show field) when info unavailable — safer for users
  // who otherwise wouldn't see what to type.
  const singleTenantMode = systemInfo?.single_tenant_mode ?? false

  const [formData, setFormData] = useState({ tenant: '', username: '', password: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (singleTenantMode && systemInfo) {
      setFormData((prev) => ({ ...prev, tenant: systemInfo.default_tenant_id }))
      return
    }
    const tenantParam = searchParams.get('tenant')
    if (tenantParam && TENANT_REGEX.test(tenantParam)) {
      setFormData((prev) => ({ ...prev, tenant: tenantParam }))
    } else {
      try {
        const saved = localStorage.getItem(LAST_TENANT_KEY)
        if (saved && TENANT_REGEX.test(saved)) {
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
      const hasAgent = data.user.roles.includes('agent')
      const defaultPath = hasAgent ? '/workspace/chat' : '/employees'
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
                <label className="mb-1 block text-sm font-medium text-foreground">
                  {t('login.tenant', locale)}
                </label>
                <input
                  type="text"
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
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('login.username', locale)}
              </label>
              <input
                type="text"
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
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('login.password', locale)}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
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
                href={`/login/forgot-password${formData.tenant ? `?tenant=${formData.tenant}` : ''}`}
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
