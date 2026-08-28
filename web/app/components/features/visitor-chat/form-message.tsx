'use client'

import { useMemo, useRef, useState } from 'react'
import { IconAlertTriangle, IconArrowLeft, IconCircleCheck, IconLoader2 } from '@tabler/icons-react'

import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import type { Locale } from '@/context/locale-store'
import type { FormMessageSource, PublicFormMessageSubmitResponse } from '@/models/form-message'
import {
  usePublicFormMessageConfig,
  useSubmitPublicFormMessage,
  useUploadPublicFormMessageFile,
} from '@/service/use-form-message'
import { publicFormFieldUid, validatePublicFormValues } from '@/lib/form-message-validation'
import { t } from '@/utils/i18n'

type Props = {
  visitorSessionToken: string
  locale: Locale
  source: FormMessageSource
  conversationPublicId?: string | null
  queueType?: 'employee_group' | null
  queueId?: number | null
  onContinueConversation?: () => void
}

const createIdempotencyKey = () =>
  globalThis.crypto?.randomUUID?.().replace(/-/g, '')
  ?? `${Date.now()}${Math.random().toString(36).slice(2)}`

function BackToBotButton({
  locale,
  disabled,
  onClick,
}: {
  locale: Locale
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex w-fit items-center gap-2 text-sm font-medium text-foreground transition-colors hover:text-primary disabled:opacity-50"
    >
      <IconArrowLeft size={18} />
      {t('chat.formMessage.backToBot', locale)}
    </button>
  )
}

export function FormMessage({
  visitorSessionToken,
  locale,
  source,
  conversationPublicId,
  queueType,
  queueId,
  onContinueConversation,
}: Props) {
  const configQuery = usePublicFormMessageConfig(visitorSessionToken, true)
  const submitMutation = useSubmitPublicFormMessage(visitorSessionToken)
  const uploadMutation = useUploadPublicFormMessageFile(visitorSessionToken)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, 'required' | 'format'>>({})
  const [result, setResult] = useState<PublicFormMessageSubmitResponse | null>(null)
  const idempotencyKey = useRef(createIdempotencyKey())
  const fieldRefs = useRef(new Map<string, HTMLDivElement>())
  const config = configQuery.data?.config
  const configVersion = configQuery.data?.version
  const initialValues = useMemo(() => {
    if (!config) return {}
    return Object.fromEntries(config.fields.flatMap((field) => {
      const defaultValue = field.definition.type_config.default_value
      return defaultValue === undefined ? [] : [[publicFormFieldUid(field), defaultValue]]
    }))
  }, [config])

  if (configQuery.isLoading) {
    return <div className="flex flex-1 items-center justify-center"><IconLoader2 size={28} className="animate-spin text-muted-foreground" /></div>
  }
  if (!config || !configVersion || configQuery.isError) {
    return <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center"><IconAlertTriangle size={36} className="text-destructive" /><p className="text-sm text-muted-foreground">{t('chat.formMessage.unavailable', locale)}</p></div>
  }
  if (result) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
        <div className="mx-auto flex w-full max-w-lg flex-col gap-5">
          {onContinueConversation && (
            <BackToBotButton locale={locale} onClick={onContinueConversation} />
          )}
          <div className="rounded-lg border border-border bg-background p-6 text-center">
            <IconCircleCheck size={44} className="mx-auto text-success" />
            <h2 className="mt-4 font-display text-xl font-semibold text-foreground">{result.success_title}</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{result.success_description}</p>
            {result.show_ticket_number && result.ticket_number && <p className="mt-4 font-mono text-sm text-foreground">{result.ticket_number}</p>}
          </div>
          <button
            type="button"
            onClick={() => {
              setValues({})
              setErrors({})
              setResult(null)
              idempotencyKey.current = createIdempotencyKey()
              submitMutation.reset()
              uploadMutation.reset()
            }}
            className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('chat.formMessage.leaveAnother', locale)}
          </button>
        </div>
      </div>
    )
  }

  const displayedValues = { ...initialValues, ...values }
  const handleSubmit = async () => {
    const nextErrors = validatePublicFormValues(config.fields, displayedValues)
    setErrors(nextErrors)
    const firstError = Object.keys(nextErrors)[0]
    if (firstError) {
      fieldRefs.current.get(firstError)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    try {
      const response = await submitMutation.mutateAsync({
        version: configVersion,
        idempotency_key: idempotencyKey.current,
        values: displayedValues,
        source,
        conversation_public_id: conversationPublicId,
        queue_type: queueType,
        queue_id: queueId,
      })
      setResult(response)
    } catch {
      // Mutation state renders the retryable form-level error below.
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
      <div className="mx-auto flex w-full max-w-lg flex-col gap-5">
        {onContinueConversation && (
          <BackToBotButton
            locale={locale}
            disabled={submitMutation.isPending}
            onClick={onContinueConversation}
          />
        )}
        <div>
          <h1 className="font-display text-xl font-semibold text-foreground">{config.title}</h1>
          {config.description && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{config.description}</p>}
        </div>
        {config.fields.map((field) => {
          const uid = publicFormFieldUid(field)
          const error = errors[uid]
          return (
            <div key={uid} ref={(node) => { if (node) fieldRefs.current.set(uid, node) }} className="flex flex-col gap-2">
              <label className="text-sm font-medium text-foreground">
                {field.definition.name}{field.required && <span className="text-destructive"> *</span>}
              </label>
              {field.definition.help_text && <p className="text-xs text-muted-foreground">{field.definition.help_text}</p>}
              <UnifiedFieldValueEditor
                field={field.definition}
                value={displayedValues[uid]}
                locale={locale}
                disabled={submitMutation.isPending}
                uploadFile={(file) => uploadMutation.mutateAsync({
                  file,
                  version: configVersion,
                  fieldRef: uid,
                })}
                onChange={(value) => {
                  setValues((current) => ({ ...current, [uid]: value }))
                  setErrors((current) => { const next = { ...current }; delete next[uid]; return next })
                }}
              />
              {error && <p className="text-xs text-destructive">{error === 'required' ? t('chat.formMessage.required', locale, { fieldName: field.definition.name }) : t('chat.formMessage.format', locale, { fieldName: field.definition.name })}</p>}
            </div>
          )
        })}
        {submitMutation.isError && <p role="alert" className="text-sm text-destructive">{t('chat.formMessage.submitFailed', locale)}</p>}
        <button type="button" disabled={submitMutation.isPending} onClick={handleSubmit} className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
          {submitMutation.isPending && <IconLoader2 size={17} className="animate-spin" />}{config.submit_label}
        </button>
      </div>
    </div>
  )
}
