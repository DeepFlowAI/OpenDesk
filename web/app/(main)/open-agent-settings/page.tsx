'use client'

import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
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
  useTestVoiceSpeedConnection,
  useUpdateOpenAgentSettings,
  useUpdateVoiceSpeedSettings,
  useVoiceSpeedSettings,
} from '@/service/use-open-agent-settings'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type FieldErrors = {
  baseUrl?: string
  apiKey?: string
}

type CredentialFormState = {
  baseUrl: string
  apiKey: string
}

type ValidationKeys = {
  baseUrlRequired: string
  baseUrlFormat: string
  apiKeyRequired: string
}

type ToastState = {
  type: 'success' | 'error'
  text: string
} | null

type CredentialSectionProps = {
  sectionId: string
  title: string
  description: string
  baseUrlLabel: string
  baseUrlPlaceholder: string
  apiKeyLabel: string
  apiKeyPlaceholder: string
  apiKeyHelp?: string
  form: CredentialFormState
  setForm: Dispatch<SetStateAction<CredentialFormState>>
  errors: FieldErrors
  showSecret: boolean
  setShowSecret: Dispatch<SetStateAction<boolean>>
  onSave: () => void
  onTest: () => void
  savePending: boolean
  testPending: boolean
  saveText: string
  savingText: string
  testText: string
  testingText: string
  showSecretText: string
  hideSecretText: string
  withDivider?: boolean
}

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

function validateCredentialForm(
  form: CredentialFormState,
  requireApiKey: boolean,
  locale: ReturnType<typeof useLocaleStore.getState>['locale'],
  keys: ValidationKeys,
): { ok: boolean; nextForm: CredentialFormState; errors: FieldErrors } {
  const errors: FieldErrors = {}
  const nextForm = {
    baseUrl: normalizeBaseUrl(form.baseUrl),
    apiKey: normalizeApiKey(form.apiKey),
  }

  if (!nextForm.baseUrl) {
    errors.baseUrl = t(keys.baseUrlRequired, locale)
  } else if (!isValidHttpUrl(nextForm.baseUrl)) {
    errors.baseUrl = t(keys.baseUrlFormat, locale)
  }

  if (requireApiKey && !nextForm.apiKey) {
    errors.apiKey = t(keys.apiKeyRequired, locale)
  }

  return { ok: Object.keys(errors).length === 0, nextForm, errors }
}

function CredentialSection({
  sectionId,
  title,
  description,
  baseUrlLabel,
  baseUrlPlaceholder,
  apiKeyLabel,
  apiKeyPlaceholder,
  apiKeyHelp,
  form,
  setForm,
  errors,
  showSecret,
  setShowSecret,
  onSave,
  onTest,
  savePending,
  testPending,
  saveText,
  savingText,
  testText,
  testingText,
  showSecretText,
  hideSecretText,
  withDivider,
}: CredentialSectionProps) {
  const disabled = savePending || testPending

  return (
    <section className={`flex flex-col gap-4 ${withDivider ? 'border-t border-border pt-6' : ''}`}>
      <div className="flex flex-col gap-1.5">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{description}</p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor={`${sectionId}-base-url`} className="text-sm font-medium text-foreground">
            {baseUrlLabel}
          </label>
          <input
            id={`${sectionId}-base-url`}
            type="text"
            value={form.baseUrl}
            onChange={(event) => setForm((value) => ({ ...value, baseUrl: event.target.value }))}
            onBlur={() => setForm((value) => ({ ...value, baseUrl: normalizeBaseUrl(value.baseUrl) }))}
            placeholder={baseUrlPlaceholder}
            className="h-10 w-full max-w-[480px] rounded-lg border border-border bg-background px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/50"
          />
          {errors.baseUrl && (
            <span className="text-sm text-destructive">{errors.baseUrl}</span>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor={`${sectionId}-api-key`} className="text-sm font-medium text-foreground">
            {apiKeyLabel}
          </label>
          <div className="relative w-full max-w-[480px]">
            <input
              id={`${sectionId}-api-key`}
              type={showSecret ? 'text' : 'password'}
              value={form.apiKey}
              onChange={(event) => setForm((value) => ({ ...value, apiKey: event.target.value }))}
              placeholder={apiKeyPlaceholder}
              className="h-10 w-full rounded-lg border border-border bg-background px-3 pr-11 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/50"
            />
            <button
              type="button"
              title={showSecret ? hideSecretText : showSecretText}
              onClick={() => setShowSecret((value) => !value)}
              className="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {showSecret ? <IconEyeOff size={17} /> : <IconEye size={17} />}
            </button>
          </div>
          {apiKeyHelp && (
            <p className="max-w-[480px] text-xs leading-5 text-muted-foreground">{apiKeyHelp}</p>
          )}
          {errors.apiKey && (
            <span className="text-sm text-destructive">{errors.apiKey}</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={disabled}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          {savePending ? savingText : saveText}
        </button>
        <button
          type="button"
          onClick={onTest}
          disabled={disabled}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-border bg-background px-5 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:opacity-60"
        >
          <IconPlugConnected size={17} />
          {testPending ? testingText : testText}
        </button>
      </div>
    </section>
  )
}

export default function OpenAgentSettingsPage() {
  const { locale } = useLocaleStore()
  const { data: openAgentSettings, isLoading: openAgentLoading } = useOpenAgentSettings()
  const { data: voiceSpeedSettings, isLoading: voiceSpeedLoading } = useVoiceSpeedSettings()
  const updateOpenAgentMutation = useUpdateOpenAgentSettings()
  const testOpenAgentMutation = useTestOpenAgentConnection()
  const updateVoiceSpeedMutation = useUpdateVoiceSpeedSettings()
  const testVoiceSpeedMutation = useTestVoiceSpeedConnection()

  const [openAgentForm, setOpenAgentForm] = useState<CredentialFormState>({ baseUrl: '', apiKey: '' })
  const [voiceSpeedForm, setVoiceSpeedForm] = useState<CredentialFormState>({ baseUrl: '', apiKey: '' })
  const [showOpenAgentSecret, setShowOpenAgentSecret] = useState(false)
  const [showVoiceSpeedSecret, setShowVoiceSpeedSecret] = useState(false)
  const [openAgentErrors, setOpenAgentErrors] = useState<FieldErrors>({})
  const [voiceSpeedErrors, setVoiceSpeedErrors] = useState<FieldErrors>({})
  const [toast, setToast] = useState<ToastState>(null)

  const hasSavedOpenAgentApiKey = openAgentSettings?.has_api_key ?? false
  const hasSavedVoiceSpeedApiKey = voiceSpeedSettings?.has_api_key ?? false

  useEffect(() => {
    if (openAgentSettings) {
      setOpenAgentForm({ baseUrl: openAgentSettings.base_url ?? '', apiKey: '' })
      setOpenAgentErrors({})
    }
  }, [openAgentSettings])

  useEffect(() => {
    if (voiceSpeedSettings) {
      setVoiceSpeedForm({ baseUrl: voiceSpeedSettings.base_url ?? '', apiKey: '' })
      setVoiceSpeedErrors({})
    }
  }, [voiceSpeedSettings])

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const handleSaveOpenAgent = async () => {
    const result = validateCredentialForm(
      openAgentForm,
      !hasSavedOpenAgentApiKey,
      locale,
      {
        baseUrlRequired: 'oa.validation.baseUrl.required',
        baseUrlFormat: 'oa.validation.baseUrl.format',
        apiKeyRequired: 'oa.validation.apiKey.required',
      },
    )
    setOpenAgentForm(result.nextForm)
    setOpenAgentErrors(result.errors)
    if (!result.ok) return

    try {
      await updateOpenAgentMutation.mutateAsync({
        base_url: result.nextForm.baseUrl,
        ...(result.nextForm.apiKey ? { api_key: result.nextForm.apiKey } : {}),
      })
      setOpenAgentForm((value) => ({ ...value, apiKey: '' }))
      setToast({ type: 'success', text: t('oa.saveSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('oa.saveFailed', locale)),
      })
    }
  }

  const handleTestOpenAgent = async () => {
    const result = validateCredentialForm(
      openAgentForm,
      !hasSavedOpenAgentApiKey,
      locale,
      {
        baseUrlRequired: 'oa.validation.baseUrl.required',
        baseUrlFormat: 'oa.validation.baseUrl.format',
        apiKeyRequired: 'oa.validation.apiKey.required',
      },
    )
    setOpenAgentForm(result.nextForm)
    setOpenAgentErrors(result.errors)
    if (!result.ok) return

    try {
      await testOpenAgentMutation.mutateAsync({
        base_url: result.nextForm.baseUrl,
        ...(result.nextForm.apiKey ? { api_key: result.nextForm.apiKey } : {}),
      })
      setToast({ type: 'success', text: t('oa.testSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('oa.testFailed', locale)),
      })
    }
  }

  const handleSaveVoiceSpeed = async () => {
    const result = validateCredentialForm(
      voiceSpeedForm,
      !hasSavedVoiceSpeedApiKey,
      locale,
      {
        baseUrlRequired: 'vs.validation.baseUrl.required',
        baseUrlFormat: 'vs.validation.baseUrl.format',
        apiKeyRequired: 'vs.validation.apiKey.required',
      },
    )
    setVoiceSpeedForm(result.nextForm)
    setVoiceSpeedErrors(result.errors)
    if (!result.ok) return

    try {
      await updateVoiceSpeedMutation.mutateAsync({
        base_url: result.nextForm.baseUrl,
        ...(result.nextForm.apiKey ? { api_key: result.nextForm.apiKey } : {}),
      })
      setVoiceSpeedForm((value) => ({ ...value, apiKey: '' }))
      setToast({ type: 'success', text: t('vs.saveSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('vs.saveFailed', locale)),
      })
    }
  }

  const handleTestVoiceSpeed = async () => {
    const result = validateCredentialForm(
      voiceSpeedForm,
      !hasSavedVoiceSpeedApiKey,
      locale,
      {
        baseUrlRequired: 'vs.validation.baseUrl.required',
        baseUrlFormat: 'vs.validation.baseUrl.format',
        apiKeyRequired: 'vs.validation.apiKey.required',
      },
    )
    setVoiceSpeedForm(result.nextForm)
    setVoiceSpeedErrors(result.errors)
    if (!result.ok) return

    try {
      await testVoiceSpeedMutation.mutateAsync({
        base_url: result.nextForm.baseUrl,
        ...(result.nextForm.apiKey ? { api_key: result.nextForm.apiKey } : {}),
      })
      setToast({ type: 'success', text: t('vs.testSuccess', locale) })
    } catch (error) {
      setToast({
        type: 'error',
        text: await getErrorMessage(error, t('vs.testFailed', locale)),
      })
    }
  }

  if (openAgentLoading || voiceSpeedLoading) {
    return (
      <div className="text-sm text-muted-foreground">{t('oa.loading', locale)}</div>
    )
  }

  const openAgentSecretPlaceholder = hasSavedOpenAgentApiKey
    ? t('oa.apiKey.placeholder.configured', locale)
    : t('oa.apiKey.placeholder.empty', locale)
  const voiceSpeedSecretPlaceholder = hasSavedVoiceSpeedApiKey
    ? t('vs.apiKey.placeholder.configured', locale)
    : t('vs.apiKey.placeholder.empty', locale)

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
              ? 'border-success/30 bg-success/10 text-success'
              : 'border-destructive/30 bg-destructive/10 text-destructive'
          }`}
        >
          {toast.type === 'success' && <IconCheck size={16} />}
          <span>{toast.text}</span>
        </div>
      )}

      <CredentialSection
        sectionId="open-agent"
        title={t('oa.section.title', locale)}
        description={t('oa.section.description', locale)}
        baseUrlLabel={t('oa.baseUrl.label', locale)}
        baseUrlPlaceholder="https://openagent.example.com"
        apiKeyLabel={t('oa.apiKey.label', locale)}
        apiKeyPlaceholder={openAgentSecretPlaceholder}
        form={openAgentForm}
        setForm={setOpenAgentForm}
        errors={openAgentErrors}
        showSecret={showOpenAgentSecret}
        setShowSecret={setShowOpenAgentSecret}
        onSave={handleSaveOpenAgent}
        onTest={handleTestOpenAgent}
        savePending={updateOpenAgentMutation.isPending}
        testPending={testOpenAgentMutation.isPending}
        saveText={t('oa.save', locale)}
        savingText={t('oa.saving', locale)}
        testText={t('oa.test', locale)}
        testingText={t('oa.testing', locale)}
        showSecretText={t('oa.apiKey.show', locale)}
        hideSecretText={t('oa.apiKey.hide', locale)}
      />

      <CredentialSection
        sectionId="voice-speed"
        title={t('vs.section.title', locale)}
        description={t('vs.section.description', locale)}
        baseUrlLabel={t('vs.baseUrl.label', locale)}
        baseUrlPlaceholder="https://voicespeed.example.com"
        apiKeyLabel={t('vs.apiKey.label', locale)}
        apiKeyPlaceholder={voiceSpeedSecretPlaceholder}
        apiKeyHelp={t('vs.apiKey.hint', locale)}
        form={voiceSpeedForm}
        setForm={setVoiceSpeedForm}
        errors={voiceSpeedErrors}
        showSecret={showVoiceSpeedSecret}
        setShowSecret={setShowVoiceSpeedSecret}
        onSave={handleSaveVoiceSpeed}
        onTest={handleTestVoiceSpeed}
        savePending={updateVoiceSpeedMutation.isPending}
        testPending={testVoiceSpeedMutation.isPending}
        saveText={t('oa.save', locale)}
        savingText={t('oa.saving', locale)}
        testText={t('oa.test', locale)}
        testingText={t('oa.testing', locale)}
        showSecretText={t('oa.apiKey.show', locale)}
        hideSecretText={t('oa.apiKey.hide', locale)}
        withDivider
      />
    </div>
  )
}
