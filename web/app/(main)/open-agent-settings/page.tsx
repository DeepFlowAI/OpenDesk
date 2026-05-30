'use client'

import { useEffect, useState } from 'react'
import { HTTPError } from 'ky'
import {
  IconCheck,
  IconEye,
  IconEyeOff,
  IconPlugConnected,
} from '@tabler/icons-react'
import {
  useOpenAgentSettings,
  useTestOpenAgentConnection,
  useUpdateOpenAgentSettings,
} from '@/service/use-open-agent-settings'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type FieldErrors = {
  baseUrl?: string
  apiKey?: string
}

type ToastState = {
  type: 'success' | 'error'
  text: string
} | null

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '')
}

function normalizeApiKey(value: string): string {
  return value.trim()
}

function isValidHttpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

async function getErrorMessage(error: unknown, fallback: string): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = await error.response.json() as { message?: string }
      return body.message || fallback
    } catch {
      return fallback
    }
  }
  return fallback
}

export default function OpenAgentSettingsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useOpenAgentSettings()
  const updateMutation = useUpdateOpenAgentSettings()
  const testMutation = useTestOpenAgentConnection()

  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [showSecret, setShowSecret] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [toast, setToast] = useState<ToastState>(null)

  const hasSavedApiKey = data?.has_api_key ?? false

  useEffect(() => {
    if (data) {
      setBaseUrl(data.base_url ?? '')
      setApiKey('')
      setErrors({})
    }
  }, [data])

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const validateForm = (requireApiKey: boolean): { ok: boolean; nextBaseUrl: string; nextApiKey: string } => {
    const nextErrors: FieldErrors = {}
    const nextBaseUrl = normalizeBaseUrl(baseUrl)
    const nextApiKey = normalizeApiKey(apiKey)

    if (!nextBaseUrl) {
      nextErrors.baseUrl = t('oa.validation.baseUrl.required', locale)
    } else if (!isValidHttpUrl(nextBaseUrl)) {
      nextErrors.baseUrl = t('oa.validation.baseUrl.format', locale)
    }

    if (requireApiKey && !nextApiKey) {
      nextErrors.apiKey = t('oa.validation.apiKey.required', locale)
    }

    setBaseUrl(nextBaseUrl)
    setErrors(nextErrors)
    return { ok: Object.keys(nextErrors).length === 0, nextBaseUrl, nextApiKey }
  }

  const handleSave = async () => {
    const result = validateForm(!hasSavedApiKey)
    if (!result.ok) return

    try {
      await updateMutation.mutateAsync({
        base_url: result.nextBaseUrl,
        ...(result.nextApiKey ? { api_key: result.nextApiKey } : {}),
      })
      setApiKey('')
      setToast({ type: 'success', text: t('oa.saveSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('oa.saveFailed', locale)),
      })
    }
  }

  const handleTest = async () => {
    const result = validateForm(!hasSavedApiKey)
    if (!result.ok) return

    try {
      await testMutation.mutateAsync({
        base_url: result.nextBaseUrl,
        ...(result.nextApiKey ? { api_key: result.nextApiKey } : {}),
      })
      setToast({ type: 'success', text: t('oa.testSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('oa.testFailed', locale)),
      })
    }
  }

  if (isLoading) {
    return (
      <div className="text-sm text-muted-foreground">{t('oa.loading', locale)}</div>
    )
  }

  const secretPlaceholder = hasSavedApiKey
    ? t('oa.apiKey.placeholder.configured', locale)
    : t('oa.apiKey.placeholder.empty', locale)

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold text-foreground">
          {t('oa.title', locale)}
        </h1>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
          {t('oa.description', locale)}
        </p>
      </div>

      {toast && (
        <div
          className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${
            toast.type === 'success'
              ? 'border-green-200 bg-green-50 text-green-700'
              : 'border-red-200 bg-red-50 text-red-700'
          }`}
        >
          {toast.type === 'success' && <IconCheck size={16} />}
          <span>{toast.text}</span>
        </div>
      )}

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="open-agent-base-url" className="text-sm font-medium text-foreground">
            {t('oa.baseUrl.label', locale)}
          </label>
          <input
            id="open-agent-base-url"
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            onBlur={() => setBaseUrl((value) => normalizeBaseUrl(value))}
            placeholder="https://openagent.example.com/"
            className="h-10 w-full max-w-[480px] rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/50"
          />
          {errors.baseUrl && (
            <span className="text-sm text-red-600">{errors.baseUrl}</span>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="open-agent-api-key" className="text-sm font-medium text-foreground">
            {t('oa.apiKey.label', locale)}
          </label>
          <div className="relative w-full max-w-[480px]">
            <input
              id="open-agent-api-key"
              type={showSecret ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={secretPlaceholder}
              className="h-10 w-full rounded-lg border border-border bg-white px-3 pr-11 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/50"
            />
            <button
              type="button"
              title={showSecret ? t('oa.apiKey.hide', locale) : t('oa.apiKey.show', locale)}
              onClick={() => setShowSecret((value) => !value)}
              className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {showSecret ? <IconEyeOff size={17} /> : <IconEye size={17} />}
            </button>
          </div>
          {errors.apiKey && (
            <span className="text-sm text-red-600">{errors.apiKey}</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={updateMutation.isPending || testMutation.isPending}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {updateMutation.isPending ? t('oa.saving', locale) : t('oa.save', locale)}
        </button>
        <button
          type="button"
          onClick={handleTest}
          disabled={updateMutation.isPending || testMutation.isPending}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-border bg-white px-5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-60"
        >
          <IconPlugConnected size={17} />
          {testMutation.isPending ? t('oa.testing', locale) : t('oa.test', locale)}
        </button>
      </div>
    </div>
  )
}
