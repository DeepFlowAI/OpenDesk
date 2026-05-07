'use client'

import { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconHeadset, IconEye, IconEyeOff } from '@tabler/icons-react'
import { useSendVerifyCode, useResetPassword } from '@/service/use-password-reset'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { sendCodeSchema, forgotPasswordSchema } from '@/utils/validators'
import { cn } from '@/lib/utils'
import { LegalFooter } from '@/components/legal-footer'

const TENANT_REGEX = /^[a-zA-Z0-9-]{2,32}$/
const LAST_TENANT_KEY = 'opendesk_last_tenant'
const COOLDOWN_SECONDS = 60
const COOLDOWN_STORAGE_KEY = 'verify_code_cooldown_end'

type FormData = {
  tenant: string
  username: string
  verifyCode: string
  newPassword: string
  confirmPassword: string
}

export default function ForgotPasswordPageWrapper() {
  return (
    <Suspense>
      <ForgotPasswordPage />
    </Suspense>
  )
}

function ForgotPasswordPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale, setLocale } = useLocaleStore()
  const sendCodeMutation = useSendVerifyCode()
  const resetMutation = useResetPassword()

  const [formData, setFormData] = useState<FormData>({
    tenant: '',
    username: '',
    verifyCode: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [showNewPwd, setShowNewPwd] = useState(false)
  const [showConfirmPwd, setShowConfirmPwd] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
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
  }, [searchParams])

  useEffect(() => {
    const endStr = sessionStorage.getItem(COOLDOWN_STORAGE_KEY)
    if (endStr) {
      const remaining = Math.ceil((parseInt(endStr, 10) - Date.now()) / 1000)
      if (remaining > 0) {
        setCountdown(remaining)
      } else {
        sessionStorage.removeItem(COOLDOWN_STORAGE_KEY)
      }
    }
  }, [])

  useEffect(() => {
    if (countdown <= 0) {
      if (timerRef.current) clearInterval(timerRef.current)
      return
    }
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          sessionStorage.removeItem(COOLDOWN_STORAGE_KEY)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [countdown])

  const validateField = useCallback(
    (field: string, value: string) => {
      const partial = { ...formData, [field]: value }

      if (['tenant', 'username'].includes(field)) {
        const result = sendCodeSchema.safeParse({ tenant: partial.tenant, username: partial.username })
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
          } else {
            setFieldErrors((prev) => {
              const next = { ...prev }
              delete next[field]
              return next
            })
          }
        }
        return
      }

      const result = forgotPasswordSchema.safeParse(partial)
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
        } else {
          setFieldErrors((prev) => {
            const next = { ...prev }
            delete next[field]
            return next
          })
        }
      }
    },
    [formData, locale]
  )

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    validateField(field, formData[field as keyof FormData])
  }

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
    setApiError('')
    setSuccessMessage('')
    if (touched[field]) {
      validateField(field, value)
    }
  }

  const mapApiError = (status: number, code?: string): string => {
    if (code === 'NOT_FOUND') {
      return t('error.account_not_found', locale)
    }
    if (code === 'RATE_LIMITED') return t('error.rate_limited', locale)
    if (code === 'INVALID_CODE') return t('error.invalid_code', locale)
    if (code === 'VALIDATION_ERROR') return t('error.email_send_failed', locale)
    if (status === 0 || status >= 500) return t('error.network', locale)
    return t('error.network', locale)
  }

  const parseApiError = async (err: unknown): Promise<{ status: number; code: string }> => {
    let status = 0
    let code = ''
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response: Response }).response
      status = response.status
      try {
        const body = await response.json()
        code = body?.code ?? ''
      } catch {
        // ignore
      }
    }
    return { status, code }
  }

  const handleSendCode = async () => {
    setApiError('')
    setSuccessMessage('')

    const codeValidation = sendCodeSchema.safeParse({
      tenant: formData.tenant,
      username: formData.username,
    })
    if (!codeValidation.success) {
      const errors: Record<string, string> = {}
      codeValidation.error.issues.forEach((issue) => {
        const field = issue.path[0] as string
        if (!errors[field]) {
          errors[field] = t(issue.message, locale)
        }
      })
      setFieldErrors((prev) => ({ ...prev, ...errors }))
      setTouched((prev) => ({ ...prev, tenant: true, username: true }))
      return
    }

    try {
      await sendCodeMutation.mutateAsync({
        tenant: formData.tenant,
        username: formData.username,
        locale,
      })
      setSuccessMessage(t('forgot.codeSent', locale))
      const endTime = Date.now() + COOLDOWN_SECONDS * 1000
      sessionStorage.setItem(COOLDOWN_STORAGE_KEY, String(endTime))
      setCountdown(COOLDOWN_SECONDS)
    } catch (err: unknown) {
      const { status, code } = await parseApiError(err)
      setApiError(mapApiError(status, code))
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setApiError('')
    setSuccessMessage('')

    const result = forgotPasswordSchema.safeParse(formData)
    if (!result.success) {
      const errors: Record<string, string> = {}
      result.error.issues.forEach((issue) => {
        const field = issue.path[0] as string
        if (!errors[field]) {
          errors[field] = t(issue.message, locale)
        }
      })
      setFieldErrors(errors)
      setTouched({
        tenant: true,
        username: true,
        verifyCode: true,
        newPassword: true,
        confirmPassword: true,
      })
      return
    }

    try {
      await resetMutation.mutateAsync({
        tenant: formData.tenant,
        username: formData.username,
        verify_code: formData.verifyCode,
        new_password: formData.newPassword,
      })
      setSuccessMessage(t('forgot.resetSuccess', locale))
      setTimeout(() => {
        router.push(`/login${formData.tenant ? `?tenant=${formData.tenant}` : ''}`)
      }, 2000)
    } catch (err: unknown) {
      const { status, code } = await parseApiError(err)
      setApiError(mapApiError(status, code))
    }
  }

  const sendCodeBtnText = () => {
    if (sendCodeMutation.isPending) return t('forgot.sending', locale)
    if (countdown > 0) return t('forgot.resend', locale, { n: countdown })
    return t('forgot.sendCode', locale)
  }

  const inputClass =
    'h-10 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50'

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
          <div className="mb-4 flex flex-col gap-2">
            <h1 className="font-sans text-2xl font-bold text-foreground">
              {t('forgot.title', locale)}
            </h1>
            <p className="text-sm text-muted-foreground">{t('forgot.subtitle', locale)}</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {/* Tenant */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('forgot.tenant', locale)}
              </label>
              <input
                type="text"
                value={formData.tenant}
                onChange={(e) => handleChange('tenant', e.target.value)}
                onBlur={() => handleBlur('tenant')}
                placeholder={t('forgot.tenant.placeholder', locale)}
                className={inputClass}
              />
              {touched.tenant && fieldErrors.tenant && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.tenant}</p>
              )}
            </div>

            {/* Username */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('forgot.username', locale)}
              </label>
              <input
                type="text"
                value={formData.username}
                onChange={(e) => handleChange('username', e.target.value)}
                onBlur={() => handleBlur('username')}
                placeholder={t('forgot.username.placeholder', locale)}
                className={inputClass}
              />
              {touched.username && fieldErrors.username && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.username}</p>
              )}
            </div>

            {/* Verify code */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('forgot.verifyCode', locale)}
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={formData.verifyCode}
                  onChange={(e) => handleChange('verifyCode', e.target.value)}
                  onBlur={() => handleBlur('verifyCode')}
                  placeholder={t('forgot.verifyCode.placeholder', locale)}
                  maxLength={6}
                  className={inputClass}
                />
                <button
                  type="button"
                  onClick={handleSendCode}
                  disabled={sendCodeMutation.isPending || countdown > 0}
                  className="flex h-10 w-[120px] shrink-0 items-center justify-center rounded-lg border border-border bg-white text-sm text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sendCodeBtnText()}
                </button>
              </div>
              {touched.verifyCode && fieldErrors.verifyCode && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.verifyCode}</p>
              )}
            </div>

            {/* New password */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('forgot.newPassword', locale)}
              </label>
              <div className="relative">
                <input
                  type={showNewPwd ? 'text' : 'password'}
                  value={formData.newPassword}
                  onChange={(e) => handleChange('newPassword', e.target.value)}
                  onBlur={() => handleBlur('newPassword')}
                  placeholder={t('forgot.newPassword.placeholder', locale)}
                  className={cn(inputClass, 'pr-10')}
                />
                <button
                  type="button"
                  onClick={() => setShowNewPwd((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                  tabIndex={-1}
                >
                  {showNewPwd ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                </button>
              </div>
              {touched.newPassword && fieldErrors.newPassword && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.newPassword}</p>
              )}
            </div>

            {/* Confirm password */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t('forgot.confirmPassword', locale)}
              </label>
              <div className="relative">
                <input
                  type={showConfirmPwd ? 'text' : 'password'}
                  value={formData.confirmPassword}
                  onChange={(e) => handleChange('confirmPassword', e.target.value)}
                  onBlur={() => handleBlur('confirmPassword')}
                  placeholder={t('forgot.confirmPassword.placeholder', locale)}
                  className={cn(inputClass, 'pr-10')}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPwd((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                  tabIndex={-1}
                >
                  {showConfirmPwd ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                </button>
              </div>
              {touched.confirmPassword && fieldErrors.confirmPassword && (
                <p className="mt-1 text-xs text-destructive/80">{fieldErrors.confirmPassword}</p>
              )}
            </div>

            {/* Success message */}
            {successMessage && (
              <div className="rounded-lg border border-success/30 bg-success/10 p-3">
                <p className="text-[13px] text-success">{successMessage}</p>
              </div>
            )}

            {/* Error alert */}
            {apiError && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3">
                <p className="text-[13px] text-destructive/80">{apiError}</p>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={resetMutation.isPending}
              className="flex h-10 w-full items-center justify-center rounded-lg bg-foreground text-sm font-semibold text-white transition-colors hover:bg-foreground/90 disabled:opacity-60"
            >
              {resetMutation.isPending
                ? t('forgot.submitting', locale)
                : t('forgot.submit', locale)}
            </button>

            {/* Back to login */}
            <div className="flex justify-center">
              <a
                href={`/login${formData.tenant ? `?tenant=${formData.tenant}` : ''}`}
                className="text-sm text-primary hover:underline"
              >
                {t('forgot.backToLogin', locale)}
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
