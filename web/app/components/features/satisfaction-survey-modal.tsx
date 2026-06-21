'use client'

import { useMemo, useState, type CSSProperties } from 'react'
import { IconLoader2, IconStar, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type {
  SatisfactionSubmissionPayload,
  SatisfactionSurveyRecord,
  SatisfactionSurveyType,
  SatisfactionTypeSettings,
  ServiceSatisfactionSettings,
} from '@/models/satisfaction-survey'

type Locale = 'zh' | 'en' | string

type FormValue = {
  rating_option_key: string
  labels: string[]
  remark: string
  resolved: boolean | null
}

type Props = {
  record: SatisfactionSurveyRecord
  locale: Locale
  submitting?: boolean
  success?: boolean
  error?: string | null
  sendButtonBgColor?: string | null
  onSubmit: (payload: SatisfactionSubmissionPayload) => Promise<void> | void
  onClose: () => void
}

const EMPTY_VALUE: FormValue = {
  rating_option_key: '',
  labels: [],
  remark: '',
  resolved: null,
}
const EMOJI_RATING_ICONS = ['😡', '😐', '😀']

function typeLabel(type: SatisfactionSurveyType, locale: Locale) {
  if (type === 'service') return locale === 'zh' ? '服务满意度' : 'Service satisfaction'
  return locale === 'zh' ? '产品满意度' : 'Product satisfaction'
}

function selectedOption(settings: SatisfactionTypeSettings, optionKey: string) {
  return settings.rating_options.find((option) => option.key === optionKey)
}

function enabledOptions(settings: SatisfactionTypeSettings) {
  return settings.rating_options.filter((option) => option.enabled)
}

function validateSection(
  type: SatisfactionSurveyType,
  settings: SatisfactionTypeSettings,
  value: FormValue,
  locale: Locale,
): string | null {
  const option = selectedOption(settings, value.rating_option_key)
  if (!option) return locale === 'zh' ? '请选择评分' : 'Please select a rating'
  if (type === 'service' && (settings as ServiceSatisfactionSettings).show_resolution && value.resolved === null) {
    return locale === 'zh' ? '请选择是否解决' : 'Please select whether the issue was resolved'
  }
  const remarkEnabled = settings.remark_enabled !== false
  if (remarkEnabled && option.remark_requirement === 'required' && !value.remark.trim()) {
    return locale === 'zh' ? '请填写备注' : 'Please enter a comment'
  }
  if (remarkEnabled && value.remark.length > 500) {
    return locale === 'zh' ? '备注最多 500 字' : 'Comment can be up to 500 characters'
  }
  return null
}

function RatingSelector({
  settings,
  value,
  onChange,
}: {
  settings: SatisfactionTypeSettings
  value: FormValue
  onChange: (value: FormValue) => void
}) {
  const options = enabledOptions(settings)
  const selectedIndex = options.findIndex((option) => option.key === value.rating_option_key)
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null

  const chooseOption = (ratingKey: string) => {
    onChange({
      ...EMPTY_VALUE,
      resolved: value.resolved,
      rating_option_key: ratingKey,
    })
  }

  if (settings.rating_mode === 'stars') {
    return (
      <div className="flex flex-col items-center gap-2">
        <div className="flex justify-center gap-1 text-2xl leading-none">
          {options.map((option, index) => {
            const active = selectedIndex >= 0 && index <= selectedIndex
            const checked = value.rating_option_key === option.key
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => chooseOption(option.key)}
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-md transition-colors focus:outline-none focus:ring-1 focus:ring-ring',
                  active
                    ? 'text-amber-400 hover:text-amber-500'
                    : 'text-muted-foreground/40 hover:bg-muted hover:text-amber-300',
                  checked && 'bg-amber-50',
                )}
                aria-label={option.name}
                aria-pressed={checked}
                title={option.name}
              >
                <IconStar size={27} stroke={1.45} className={active ? 'fill-current' : ''} />
              </button>
            )
          })}
        </div>
        <span className="min-h-5 text-sm font-medium text-foreground">
          {selected?.name ?? ''}
        </span>
      </div>
    )
  }

  if (settings.rating_mode === 'emoji') {
    return (
      <div className="flex flex-col items-center gap-2">
        <div className="flex justify-center gap-3">
          {options.map((option, index) => {
            const checked = value.rating_option_key === option.key
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => chooseOption(option.key)}
                className={cn(
                  'flex h-14 w-14 items-center justify-center rounded-md border text-2xl transition-colors focus:outline-none focus:ring-1 focus:ring-ring',
                  checked
                    ? 'border-foreground bg-muted text-foreground shadow-sm'
                    : 'border-border bg-background text-foreground hover:bg-muted/70',
                )}
                aria-label={option.name}
                aria-pressed={checked}
                title={option.name}
              >
                {EMOJI_RATING_ICONS[index] ?? '😀'}
              </button>
            )
          })}
        </div>
        <span className="min-h-5 text-sm font-medium text-foreground">
          {selected?.name ?? ''}
        </span>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {options.map((option) => {
        const checked = value.rating_option_key === option.key
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => chooseOption(option.key)}
            className={cn(
              'rounded-md border px-3 py-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-ring',
              checked
                ? 'border-foreground bg-muted text-foreground'
                : 'border-border bg-background text-foreground hover:bg-muted',
            )}
            aria-pressed={checked}
          >
            {option.name}
          </button>
        )
      })}
    </div>
  )
}

function ResolutionSelector({
  locale,
  value,
  onChange,
}: {
  locale: Locale
  value: FormValue
  onChange: (value: FormValue) => void
}) {
  const options = [
    { label: locale === 'zh' ? '解决' : 'Resolved', value: true },
    { label: locale === 'zh' ? '未解决' : 'Unresolved', value: false },
  ]

  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <span className="text-sm font-medium text-foreground">
        {locale === 'zh' ? '是否解决' : 'Issue resolved'}
      </span>
      <div className="flex justify-center gap-2">
        {options.map((item) => (
          <button
            key={String(item.value)}
            type="button"
            onClick={() => onChange({ ...value, resolved: item.value })}
            className={cn(
              'rounded-full px-4 py-1.5 text-sm font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-ring',
              value.resolved === item.value
                ? 'bg-primary text-primary-foreground'
                : 'border border-border bg-white text-foreground hover:bg-accent',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function LabelSelector({
  labels,
  value,
  multiple,
  onToggle,
}: {
  labels: string[]
  value: FormValue
  multiple: boolean
  onToggle: (label: string) => void
}) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {labels.map((label) => {
        const selected = value.labels.includes(label)
        return (
          <button
            key={label}
            type="button"
            onClick={() => onToggle(label)}
            className={cn(
              'rounded-xl px-2.5 py-1 text-xs font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-ring',
              selected
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground/80 hover:text-foreground',
            )}
            aria-pressed={selected}
            aria-label={multiple ? label : undefined}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

function SectionEditor({
  type,
  settings,
  locale,
  value,
  error,
  onChange,
}: {
  type: SatisfactionSurveyType
  settings: SatisfactionTypeSettings
  locale: Locale
  value: FormValue
  error: string | null
  onChange: (value: FormValue) => void
}) {
  const option = selectedOption(settings, value.rating_option_key)
  const labels = option?.labels ?? []
  const showRemark = Boolean(option && settings.remark_enabled && option.remark_requirement !== 'hidden')
  const showResolution = type === 'service' && (settings as ServiceSatisfactionSettings).show_resolution

  const toggleLabel = (label: string) => {
    const multiple = settings.tag_selection_mode === 'multiple'
    const exists = value.labels.includes(label)
    const labels = multiple
      ? exists
        ? value.labels.filter((item) => item !== label)
        : [...value.labels, label]
      : exists
        ? []
        : [label]
    onChange({ ...value, labels })
  }

  return (
    <section className="flex flex-col gap-4 py-5">
      <div className="text-center">
        <h3 className="text-sm font-semibold text-foreground">
          {settings.section_title || typeLabel(type, locale)}
        </h3>
        {settings.popup_title && (
          <p className="mt-1 text-sm text-muted-foreground">{settings.popup_title}</p>
        )}
      </div>

      {showResolution && (
        <ResolutionSelector locale={locale} value={value} onChange={onChange} />
      )}

      <RatingSelector settings={settings} value={value} onChange={onChange} />

      {labels.length > 0 && (
        <LabelSelector
          labels={labels}
          value={value}
          multiple={settings.tag_selection_mode === 'multiple'}
          onToggle={toggleLabel}
        />
      )}

      {showRemark && (
        <textarea
          value={value.remark}
          onChange={(e) => onChange({ ...value, remark: e.target.value.slice(0, 500) })}
          placeholder={settings.remark_placeholder || (locale === 'zh' ? '请输入您的评价（选填）' : 'Share your feedback (optional)')}
          className="min-h-20 w-full resize-none rounded-md border border-border bg-white p-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
        />
      )}

      {error && <p className="text-center text-xs text-destructive">{error}</p>}
    </section>
  )
}

export function SatisfactionSurveyModal({
  record,
  locale,
  submitting,
  success,
  error,
  sendButtonBgColor,
  onSubmit,
  onClose,
}: Props) {
  const [service, setService] = useState<FormValue>(EMPTY_VALUE)
  const [product, setProduct] = useState<FormValue>(EMPTY_VALUE)
  const [sectionErrors, setSectionErrors] = useState<Record<string, string | null>>({})
  const snapshot = record.config_snapshot
  const surveyTypes = record.survey_types
  const modalTitle = locale === 'zh' ? '满意度评价' : 'Rate your experience'
  const submitText = locale === 'zh' ? '提交评价' : 'Submit'
  const laterText = locale === 'zh' ? '稍后评价' : 'Maybe later'
  const sendButtonStyle = {
    '--opendesk-send-button-bg': sendButtonBgColor || 'var(--color-primary)',
  } as CSSProperties

  const sections = useMemo(
    () =>
      surveyTypes
        .map((type) => ({
          type,
          settings: type === 'service' ? snapshot.service : snapshot.product,
          value: type === 'service' ? service : product,
        }))
        .filter((section) => section.settings.enabled),
    [product, service, snapshot.product, snapshot.service, surveyTypes],
  )

  const handleSubmit = async () => {
    const nextErrors: Record<string, string | null> = {}
    for (const section of sections) {
      nextErrors[section.type] = validateSection(section.type, section.settings, section.value, locale)
    }
    setSectionErrors(nextErrors)
    if (Object.values(nextErrors).some(Boolean)) return

    const payload: SatisfactionSubmissionPayload = {}
    if (surveyTypes.includes('service')) {
      payload.service = {
        rating_option_key: service.rating_option_key,
        labels: service.labels,
        remark: service.remark || null,
        resolved: service.resolved,
      }
    }
    if (surveyTypes.includes('product')) {
      payload.product = {
        rating_option_key: product.rating_option_key,
        labels: product.labels,
        remark: product.remark || null,
      }
    }
    await onSubmit(payload)
  }

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/40 px-4">
      <div className="max-h-[calc(100%-32px)] w-full max-w-[400px] overflow-y-auto rounded-2xl border border-border bg-background shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background px-4 py-3">
          <h2 className="text-base font-semibold text-foreground">{modalTitle}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={locale === 'zh' ? '关闭' : 'Close'}
          >
            <IconX size={18} />
          </button>
        </div>

        <div className="px-4 py-1">
          {success ? (
            <div className="py-10 text-center text-sm font-medium text-foreground">
              {locale === 'zh' ? '感谢评价' : 'Thanks for your feedback'}
            </div>
          ) : (
            <>
              {sections.map((section, index) => (
                <div key={section.type} className={cn(index > 0 && 'border-t border-border')}>
                  <SectionEditor
                    type={section.type}
                    settings={section.settings}
                    locale={locale}
                    value={section.value}
                    error={sectionErrors[section.type] || null}
                    onChange={section.type === 'service' ? setService : setProduct}
                  />
                </div>
              ))}
              {error && <p className="pb-3 text-center text-xs text-destructive">{error}</p>}
            </>
          )}
        </div>

        {!success && (
          <div className="flex gap-2 border-t border-border p-4">
            <button
              type="button"
              onClick={onClose}
              className="h-9 flex-1 rounded-lg border border-border bg-background text-sm font-medium text-foreground hover:bg-muted"
            >
              {laterText}
            </button>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting}
              className="flex h-9 flex-1 items-center justify-center gap-1 rounded-lg bg-[var(--opendesk-send-button-bg)] text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              style={sendButtonStyle}
            >
              {submitting && <IconLoader2 size={15} className="animate-spin" />}
              {submitText}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
