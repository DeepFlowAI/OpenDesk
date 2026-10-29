'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconChevronDown, IconLoader2 } from '@tabler/icons-react'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { isCnMobileNumber } from '@/utils/validators'
import { useSendSms } from '@/service/use-sms'
import type { SmsWorkspaceTemplateItem } from '@/models/sms'
import { CallConfirmDialog } from './call-confirm-dialog'
import { cn } from '@/lib/utils'

// Provider error codes meaning the shared channel cannot serve right now
// (insufficient balance, rate limiting); shown with a dedicated message.
const CHANNEL_UNAVAILABLE_CODES = new Set(['isv.AMOUNT_NOT_ENOUGH', 'isv.BUSINESS_LIMIT_CONTROL'])

const DEFAULT_VARIABLE_MAX_LENGTH = 30

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultPhone: string
  phoneReadonly: boolean
  callId?: string | null
  templates: SmsWorkspaceTemplateItem[]
}

function renderPreviewBody(body: string, values: Record<string, string>): string {
  let rendered = body
  for (const [key, value] of Object.entries(values)) {
    if (value) rendered = rendered.replaceAll(`{${key}}`, value)
  }
  return rendered
}

export function SendSmsDialog({
  open,
  onOpenChange,
  defaultPhone,
  phoneReadonly,
  callId,
  templates,
}: Props) {
  const { locale } = useLocaleStore()
  const sendMutation = useSendSms()

  const [phone, setPhone] = useState(defaultPhone)
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [phoneError, setPhoneError] = useState<string | null>(null)
  const [templateError, setTemplateError] = useState<string | null>(null)
  const [variableErrors, setVariableErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [confirmDiscard, setConfirmDiscard] = useState(false)

  const template = useMemo(
    () => templates.find((item) => item.id === templateId) ?? null,
    [templates, templateId],
  )
  const submitting = sendMutation.isPending

  useEffect(() => {
    if (open) {
      setPhone(defaultPhone)
      setTemplateId(null)
      setValues({})
      setPhoneError(null)
      setTemplateError(null)
      setVariableErrors({})
      setSubmitError(null)
      setConfirmDiscard(false)
    }
  }, [open, defaultPhone])

  const hasFilledVariables = Object.values(values).some((value) => value.trim().length > 0)

  const requestClose = () => {
    if (submitting) return
    if (hasFilledVariables) setConfirmDiscard(true)
    else onOpenChange(false)
  }

  const handleSend = async () => {
    const nextPhoneError = isCnMobileNumber(phone)
      ? null
      : t('sms.send.invalidPhone', locale)
    const nextTemplateError = template ? null : t('sms.send.templateRequired', locale)
    const nextVariableErrors: Record<string, string> = {}
    if (template) {
      for (const def of template.variables) {
        if (def.required && !(values[def.key] ?? '').trim()) {
          nextVariableErrors[def.key] = t('sms.send.variableRequired', locale, {
            label: def.label,
          })
        }
      }
    }
    setPhoneError(nextPhoneError)
    setTemplateError(nextTemplateError)
    setVariableErrors(nextVariableErrors)
    if (
      nextPhoneError ||
      nextTemplateError ||
      Object.keys(nextVariableErrors).length > 0 ||
      !template
    )
      return

    const cleanedValues = Object.fromEntries(
      Object.entries(values)
        .map(([key, value]) => [key, value.trim()] as const)
        .filter(([, value]) => value.length > 0),
    )
    try {
      const result = await sendMutation.mutateAsync({
        phone: phone.trim(),
        template_id: template.id,
        variables: cleanedValues,
        call_id: callId ?? null,
        client_request_id: crypto.randomUUID(),
      })
      if (result.status === 'failed') {
        setSubmitError(
          result.error_code && CHANNEL_UNAVAILABLE_CODES.has(result.error_code)
            ? t('sms.send.channelUnavailable', locale)
            : result.fail_reason
              ? `${t('sms.send.failed', locale)}: ${result.fail_reason}`
              : t('sms.send.failed', locale),
        )
        return
      }
      toast.success(t('sms.send.submitted', locale))
      onOpenChange(false)
    } catch {
      setSubmitError(t('sms.send.failed', locale))
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => { if (!next) requestClose() }}>
        <DialogContent className="grid-cols-[minmax(0,1fr)] gap-0 p-0 sm:max-w-[520px]">
          <DialogHeader className="border-b border-border px-5 py-4">
            <DialogTitle>{t('sms.send.title', locale)}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 px-5 py-4">
            {templates.length === 0 && (
              <div
                role="alert"
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
              >
                {t('sms.send.noTemplates', locale)}
              </div>
            )}
            {submitError && (
              <div
                role="alert"
                className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
              >
                {submitError}
              </div>
            )}

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                {t('sms.send.phone', locale)}{phoneReadonly ? '' : ' *'}
              </label>
              <input
                type="text"
                inputMode="tel"
                value={phone}
                readOnly={phoneReadonly}
                onChange={(event) => {
                  setPhone(event.target.value)
                  setPhoneError(null)
                }}
                className={cn(
                  'h-10 w-full rounded-md border border-border px-3 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30',
                  phoneReadonly && 'bg-muted/40',
                  phoneError && 'border-red-400',
                )}
              />
              {phoneReadonly ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {t('sms.send.phoneReadonlyHint', locale)}
                </p>
              ) : phoneError ? (
                <p className="mt-1 text-xs text-red-600">{phoneError}</p>
              ) : null}
            </div>

            <div>
              <label
                className={cn(
                  'mb-1.5 block text-xs font-medium',
                  templateError ? 'text-red-600' : 'text-muted-foreground',
                )}
              >
                {t('sms.send.template', locale)} *
              </label>
              <div className="relative">
                <select
                  value={templateId ?? ''}
                  onChange={(event) => {
                    setTemplateId(event.target.value ? Number(event.target.value) : null)
                    setTemplateError(null)
                    setVariableErrors({})
                  }}
                  className={cn(
                    'h-10 w-full appearance-none rounded-md border border-border bg-background px-3 pr-8 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30',
                    templateId === null && 'text-muted-foreground',
                    templateError && 'border-red-400',
                  )}
                >
                  <option value="">{t('sms.send.templatePlaceholder', locale)}</option>
                  {templates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {`${item.name}（${item.sign_name}）`}
                    </option>
                  ))}
                </select>
                <IconChevronDown
                  size={14}
                  className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
              </div>
              {templateError && <p className="mt-1 text-xs text-red-600">{templateError}</p>}
            </div>

            {template?.variables.map((def) => {
              const error = variableErrors[def.key]
              return (
                <div key={def.key}>
                  <label
                    className={cn(
                      'mb-1.5 block text-xs font-medium',
                      error ? 'text-red-600' : 'text-muted-foreground',
                    )}
                  >
                    {def.label}{def.required ? ' *' : ''}
                  </label>
                  <input
                    type="text"
                    value={values[def.key] ?? ''}
                    maxLength={def.max_length ?? DEFAULT_VARIABLE_MAX_LENGTH}
                    onChange={(event) => {
                      setValues((prev) => ({ ...prev, [def.key]: event.target.value }))
                      setVariableErrors((prev) => {
                        if (!prev[def.key]) return prev
                        const next = { ...prev }
                        delete next[def.key]
                        return next
                      })
                    }}
                    className={cn(
                      'h-10 w-full rounded-md border border-border px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30',
                      error && 'border-red-400',
                    )}
                  />
                  {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
                </div>
              )
            })}

            {template && (
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">
                  {t('sms.send.preview', locale)}
                </div>
                <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                  {`【${template.sign_name}】${renderPreviewBody(template.body, values)}`}
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="border-t border-border px-5 py-4">
            <Button variant="outline" onClick={requestClose} disabled={submitting}>
              {t('sms.send.cancel', locale)}
            </Button>
            <Button
              onClick={() => void handleSend()}
              disabled={submitting || templates.length === 0}
            >
              {submitting && <IconLoader2 size={14} className="mr-1 animate-spin" />}
              {submitting ? t('sms.send.sending', locale) : t('sms.send.submit', locale)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CallConfirmDialog
        open={confirmDiscard}
        title={t('sms.send.discardConfirmTitle', locale)}
        body={t('sms.send.discardConfirmBody', locale)}
        confirmLabel={t('sms.send.discardConfirmOk', locale)}
        onClose={() => setConfirmDiscard(false)}
        onConfirm={() => {
          setConfirmDiscard(false)
          onOpenChange(false)
        }}
      />
    </>
  )
}
