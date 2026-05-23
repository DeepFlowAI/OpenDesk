'use client'

import { useEffect, useMemo, useState, type KeyboardEvent } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus, Trash2, X } from 'lucide-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import {
  useSatisfactionSurveyConfig,
  useSaveSatisfactionSurveyConfig,
} from '@/service/use-satisfaction-survey'
import type {
  ProductSatisfactionSettings,
  SatisfactionRatingMode,
  SatisfactionRatingOption,
  SatisfactionRemarkRequirement,
  SatisfactionSurveyConfig,
  SatisfactionSurveyType,
  SatisfactionTypeSettings,
  SaveSatisfactionSurveyPayload,
  ServiceSatisfactionSettings,
} from '@/models/satisfaction-survey'
import {
  SATISFACTION_TRIGGER_MODES,
} from '@/models/satisfaction-survey'

type DraftConfig = SaveSatisfactionSurveyPayload

const RATING_MODES: SatisfactionRatingMode[] = ['stars', 'text', 'emoji']
const REMARK_REQUIREMENTS: SatisfactionRemarkRequirement[] = ['hidden', 'optional', 'required']

function text(locale: Locale, key: string, params?: Record<string, string | number>) {
  return t(`sat.${key}`, locale, params)
}

function optionKey(prefix: string, index: number) {
  return `${prefix}-${index}-${Math.random().toString(36).slice(2, 8)}`
}

function defaultOptions(kind: SatisfactionSurveyType, mode: SatisfactionRatingMode): SatisfactionRatingOption[] {
  const positive =
    kind === 'service'
      ? ['响应及时', '态度友好', '解决问题', '表达清晰']
      : ['易于使用', '功能清晰', '速度快', '符合预期']
  const negative =
    kind === 'service'
      ? ['等待太久', '没有解决', '态度不好', '重复沟通']
      : ['操作复杂', '功能缺失', '加载慢', '不符合预期']

  const rows =
    mode === 'emoji'
      ? [
          ['不满意', 2, negative, 'required'],
          ['一般', 6, [], 'optional'],
          ['满意', 10, positive, 'hidden'],
        ]
      : mode === 'text'
        ? [
            ['超级满意', 10, positive, 'hidden'],
            ['满意', 8, positive, 'optional'],
            ['一般', 6, [], 'optional'],
            ['不满意', 4, negative, 'required'],
            ['非常不满意', 2, negative, 'required'],
          ]
        : [
            ['非常不满意', 2, negative, 'required'],
            ['不满意', 4, negative, 'required'],
            ['一般', 6, [], 'optional'],
            ['满意', 8, positive, 'optional'],
            ['非常满意', 10, positive, 'hidden'],
          ]

  return rows.map(([name, score, labels, remark], index) => ({
    key: optionKey(`${kind}-${mode}`, index + 1),
    enabled: true,
    name: String(name),
    is_default: false,
    score: Number(score),
    labels: labels as string[],
    remark_requirement: remark as SatisfactionRemarkRequirement,
  }))
}

function stripMeta(config: SatisfactionSurveyConfig): DraftConfig {
  return {
    name: config.name,
    enabled: config.enabled,
    triggers: { ...config.triggers },
    service: {
      ...config.service,
      rating_options: config.service.rating_options.map((option) => ({ ...option, labels: [...option.labels] })),
    },
    product: {
      ...config.product,
      rating_options: config.product.rating_options.map((option) => ({ ...option, labels: [...option.labels] })),
    },
  }
}

function serializeDraft(draft: DraftConfig) {
  return JSON.stringify(draft)
}

function firstActiveOption(settings: SatisfactionTypeSettings): SatisfactionRatingOption | null {
  const enabled = settings.rating_options.filter((option) => option.enabled)
  return enabled.find((option) => option.is_default) ?? enabled[0] ?? null
}

function validateTypeSettings(settings: SatisfactionTypeSettings, typeLabel: string, locale: Locale): string | null {
  if (!settings.enabled) return null
  if (!settings.section_title.trim()) return text(locale, 'validation.sectionTitle', { type: typeLabel })
  if (settings.section_title.trim().length > 32) return text(locale, 'validation.sectionTitleLength', { type: typeLabel })
  if (!settings.popup_title.trim()) return text(locale, 'validation.popupTitle', { type: typeLabel })
  if (settings.popup_title.trim().length > 50) return text(locale, 'validation.popupTitleLength', { type: typeLabel })
  if (settings.remark_placeholder.trim().length > 50) return text(locale, 'validation.remarkPlaceholder')

  const enabledOptions = settings.rating_options.filter((option) => option.enabled)
  if (enabledOptions.length < 2) return text(locale, 'validation.optionsMin', { type: typeLabel })
  const names = enabledOptions.map((option) => option.name.trim())
  if (names.some((name) => !name)) return text(locale, 'validation.optionName')
  if (new Set(names).size !== names.length) return text(locale, 'validation.optionDuplicate')
  if (enabledOptions.some((option) => !Number.isInteger(option.score) || option.score < 1)) {
    return text(locale, 'validation.optionScore')
  }
  const defaults = settings.rating_options.filter((option) => option.is_default)
  if (defaults.length > 1) return text(locale, 'validation.defaultSingle')
  if (defaults[0] && !defaults[0].enabled) return text(locale, 'validation.defaultEnabled')
  return null
}

function validateDraft(draft: DraftConfig, locale: Locale): string | null {
  if (!draft.name.trim()) return text(locale, 'validation.name')
  if (draft.name.trim().length > 64) return text(locale, 'validation.nameLength')
  if (
    !draft.triggers.agent_invite &&
    !draft.triggers.user_initiated &&
    !draft.triggers.session_end_invite
  ) {
    return text(locale, 'validation.trigger')
  }
  if (!draft.service.enabled && !draft.product.enabled) return text(locale, 'validation.type')
  return (
    validateTypeSettings(draft.service, text(locale, 'service'), locale) ??
    validateTypeSettings(draft.product, text(locale, 'product'), locale)
  )
}

function FieldLabel({ children, required }: { children: string; required?: boolean }) {
  return (
    <span className="text-sm font-medium text-foreground">
      {children}
      {required && <span className="ml-1 text-destructive">*</span>}
    </span>
  )
}

function TextInput({
  value,
  onChange,
  placeholder,
  disabled,
  className,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={cn(
        'h-10 w-full rounded-md border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:bg-muted disabled:text-muted-foreground',
        className,
      )}
    />
  )
}

function NumberInput({
  value,
  onChange,
  disabled,
}: {
  value: number
  onChange: (value: number) => void
  disabled?: boolean
}) {
  return (
    <input
      type="number"
      min={1}
      value={Number.isFinite(value) ? value : ''}
      onChange={(event) => onChange(Number.parseInt(event.target.value || '0', 10))}
      disabled={disabled}
      className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:bg-muted disabled:text-muted-foreground"
    />
  )
}

const MAX_LABELS = 20
const MAX_LABEL_LENGTH = 32

function TagInput({
  labels,
  onChange,
  placeholder,
  disabled,
}: {
  labels: string[]
  onChange: (labels: string[]) => void
  placeholder?: string
  disabled?: boolean
}) {
  const [inputValue, setInputValue] = useState('')

  const addLabel = (raw: string) => {
    const value = raw.trim().slice(0, MAX_LABEL_LENGTH)
    if (!value || labels.includes(value) || labels.length >= MAX_LABELS) return
    onChange([...labels, value])
    setInputValue('')
  }

  const removeLabel = (index: number) => {
    onChange(labels.filter((_, labelIndex) => labelIndex !== index))
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      addLabel(inputValue)
      return
    }
    if (event.key === 'Backspace' && !inputValue && labels.length > 0) {
      removeLabel(labels.length - 1)
    }
  }

  return (
    <div
      className={cn(
        'flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-border bg-white px-2 py-1 focus-within:outline-none focus-within:ring-1 focus-within:ring-ring',
        disabled && 'bg-muted',
      )}
    >
      {labels.map((label, index) => (
        <span
          key={`${label}-${index}`}
          className="inline-flex max-w-full items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs text-foreground"
        >
          <span className="truncate">{label}</span>
          {!disabled && (
            <button
              type="button"
              onClick={() => removeLabel(index)}
              className="inline-flex shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground"
              aria-label={`Remove ${label}`}
            >
              <X size={12} />
            </button>
          )}
        </span>
      ))}
      <input
        value={inputValue}
        onChange={(event) => setInputValue(event.target.value.slice(0, MAX_LABEL_LENGTH))}
        onKeyDown={handleKeyDown}
        disabled={disabled || labels.length >= MAX_LABELS}
        placeholder={labels.length === 0 ? placeholder : undefined}
        className="min-w-[72px] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:text-muted-foreground"
      />
    </div>
  )
}

function TypeSettingsEditor({
  kind,
  settings,
  locale,
  onChange,
}: {
  kind: SatisfactionSurveyType
  settings: ServiceSatisfactionSettings | ProductSatisfactionSettings
  locale: Locale
  onChange: (next: ServiceSatisfactionSettings | ProductSatisfactionSettings) => void
}) {
  const isService = kind === 'service'
  const disabled = !settings.enabled

  const updateOption = (index: number, patch: Partial<SatisfactionRatingOption>) => {
    onChange({
      ...settings,
      rating_options: settings.rating_options.map((option, optionIndex) =>
        optionIndex === index ? { ...option, ...patch } : option,
      ),
    })
  }

  const setDefault = (index: number) => {
    onChange({
      ...settings,
      rating_options: settings.rating_options.map((option, optionIndex) => ({
        ...option,
        enabled: optionIndex === index ? true : option.enabled,
        is_default: optionIndex === index,
      })),
    })
  }

  const deleteOption = (index: number) => {
    if (settings.rating_options.length <= 2) return
    onChange({
      ...settings,
      rating_options: settings.rating_options.filter((_, optionIndex) => optionIndex !== index),
    })
  }

  const addOption = () => {
    onChange({
      ...settings,
      rating_options: [
        ...settings.rating_options,
        {
          key: optionKey(`${kind}-custom`, settings.rating_options.length + 1),
          enabled: true,
          name: text(locale, 'option.new'),
          is_default: false,
          score: 10,
          labels: [],
          remark_requirement: 'optional',
        },
      ],
    })
  }

  const defaultOptionIndex = settings.rating_options.findIndex((option) => option.is_default)
  const defaultOptionValue = defaultOptionIndex >= 0 ? String(defaultOptionIndex) : ''
  const canCustomizeOptions = settings.rating_mode === 'text'
  const optionRowGridClass = canCustomizeOptions
    ? 'grid min-w-[820px] grid-cols-[56px_1fr_64px_80px_180px_120px_52px] items-center gap-3'
    : 'grid min-w-[768px] grid-cols-[56px_1fr_64px_80px_180px_120px] items-center gap-3'

  return (
    <section className="border-t border-border pt-7">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Switch checked={settings.enabled} onCheckedChange={(enabled) => onChange({ ...settings, enabled })} />
          <h2 className="text-base font-semibold text-foreground">
            {isService ? text(locale, 'service') : text(locale, 'product')}
          </h2>
        </div>
      </div>

      <div className={cn('mt-5 flex flex-col gap-5', disabled && 'opacity-50')}>
        {isService && (
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <FieldLabel>{text(locale, 'resolution')}</FieldLabel>
              <span className="text-xs text-muted-foreground">{text(locale, 'resolution.fixed')}</span>
            </div>
            <Switch
              checked={(settings as ServiceSatisfactionSettings).show_resolution}
              disabled={disabled}
              onCheckedChange={(show_resolution) =>
                onChange({ ...(settings as ServiceSatisfactionSettings), show_resolution })
              }
            />
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <FieldLabel required>{text(locale, 'sectionTitle')}</FieldLabel>
            <TextInput
              value={settings.section_title}
              onChange={(section_title) => onChange({ ...settings, section_title })}
              disabled={disabled}
              placeholder={text(locale, 'sectionTitle')}
            />
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel required>{text(locale, 'popupTitle')}</FieldLabel>
            <TextInput
              value={settings.popup_title}
              onChange={(popup_title) => onChange({ ...settings, popup_title })}
              disabled={disabled}
              placeholder={text(locale, 'popupTitle')}
            />
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <FieldLabel required>{text(locale, 'ratingMode')}</FieldLabel>
          <div className="inline-flex w-fit rounded-md bg-muted p-1">
            {RATING_MODES.map((mode) => (
              <button
                key={mode}
                type="button"
                disabled={disabled}
                onClick={() =>
                  onChange({
                    ...settings,
                    rating_mode: mode,
                    rating_options: defaultOptions(kind, mode),
                  })
                }
                className={cn(
                  'h-8 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors disabled:opacity-50',
                  settings.rating_mode === mode && 'bg-white text-foreground shadow-sm',
                )}
              >
                {text(locale, `ratingMode.${mode}`)}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-4">
            <FieldLabel required>{text(locale, 'options')}</FieldLabel>
            {canCustomizeOptions && (
              <button
                type="button"
                onClick={addOption}
                disabled={disabled}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
              >
                <Plus size={15} />
                {text(locale, 'option.add')}
              </button>
            )}
          </div>
          <div className="overflow-x-auto rounded-md border border-border">
            <div className={cn(optionRowGridClass, 'border-b border-border bg-muted px-4 py-2 text-xs font-semibold text-foreground/70')}>
              <span>{text(locale, 'option.enabled')}</span>
              <span>{text(locale, 'option.name')}</span>
              <span>{text(locale, 'option.default')}</span>
              <span>{text(locale, 'option.score')}</span>
              <span>{text(locale, 'option.labels')}</span>
              <span>{text(locale, 'option.remark')}</span>
              {canCustomizeOptions && <span />}
            </div>
            <RadioGroup
              value={defaultOptionValue}
              onValueChange={(value) => setDefault(Number(value))}
              disabled={disabled}
              className="contents"
            >
            {settings.rating_options.map((option, index) => (
              <div
                key={option.key || index}
                className={cn(optionRowGridClass, 'border-b border-border px-4 py-2 last:border-b-0')}
              >
                <Checkbox
                  checked={option.enabled}
                  disabled={disabled}
                  onCheckedChange={(checked) => updateOption(index, { enabled: checked === true })}
                  aria-label={text(locale, 'option.enabled')}
                />
                <TextInput
                  value={option.name}
                  onChange={(name) => updateOption(index, { name })}
                  disabled={disabled || !option.enabled}
                  className="h-9"
                />
                <RadioGroupItem
                  value={String(index)}
                  disabled={disabled}
                  aria-label={text(locale, 'option.default')}
                />
                <NumberInput
                  value={option.score}
                  onChange={(score) => updateOption(index, { score })}
                  disabled={disabled || !option.enabled}
                />
                <TagInput
                  labels={option.labels}
                  onChange={(labels) => updateOption(index, { labels })}
                  disabled={disabled || !option.enabled}
                  placeholder={text(locale, 'option.labels.placeholder')}
                />
                <select
                  value={option.remark_requirement}
                  disabled={disabled || !option.enabled}
                  onChange={(event) =>
                    updateOption(index, { remark_requirement: event.target.value as SatisfactionRemarkRequirement })
                  }
                  className="h-9 rounded-md border border-border bg-white px-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:bg-muted disabled:text-muted-foreground"
                >
                  {REMARK_REQUIREMENTS.map((requirement) => (
                    <option key={requirement} value={requirement}>
                      {text(locale, `remark.${requirement}`)}
                    </option>
                  ))}
                </select>
                {canCustomizeOptions && (
                  <button
                    type="button"
                    onClick={() => deleteOption(index)}
                    disabled={disabled || settings.rating_options.length <= 2}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-destructive disabled:opacity-40"
                    aria-label={text(locale, 'option.delete')}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            ))}
            </RadioGroup>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <FieldLabel>{text(locale, 'tagSelection')}</FieldLabel>
          <RadioGroup
            value={settings.tag_selection_mode}
            onValueChange={(mode) =>
              onChange({ ...settings, tag_selection_mode: mode as 'single' | 'multiple' })
            }
            disabled={disabled}
            className="flex h-10 items-center gap-5"
          >
            {(['single', 'multiple'] as const).map((mode) => (
              <label key={mode} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={mode} />
                {text(locale, `tagSelection.${mode}`)}
              </label>
            ))}
          </RadioGroup>
        </div>

        <div className="flex items-center justify-between gap-4">
          <FieldLabel>{text(locale, 'remarkToggle')}</FieldLabel>
          <Switch
            checked={settings.remark_enabled}
            disabled={disabled}
            onCheckedChange={(remark_enabled) => onChange({ ...settings, remark_enabled })}
          />
        </div>

        <div className="flex flex-col gap-2">
          <FieldLabel>{text(locale, 'remarkPlaceholder')}</FieldLabel>
          <TextInput
            value={settings.remark_placeholder}
            onChange={(remark_placeholder) => onChange({ ...settings, remark_placeholder })}
            disabled={disabled || !settings.remark_enabled}
            placeholder={text(locale, 'remarkPlaceholder.placeholder')}
          />
        </div>
      </div>
    </section>
  )
}

function RatingPreview({ settings }: { settings: SatisfactionTypeSettings }) {
  const selected = firstActiveOption(settings)
  if (!selected) return null

  if (settings.rating_mode === 'stars') {
    const enabledOptions = settings.rating_options.filter((option) => option.enabled)
    const selectedIndex = enabledOptions.findIndex((option) => option.key === selected.key)
    return (
      <div className="flex flex-col items-center gap-2">
        <div className="flex gap-1 text-2xl leading-none">
          {enabledOptions.map((option, index) => (
            <span key={option.key} className={index <= selectedIndex ? 'text-amber-400' : 'text-muted-foreground/40'}>
              ★
            </span>
          ))}
        </div>
        <span className="text-sm font-medium text-foreground">{selected.name}</span>
      </div>
    )
  }

  if (settings.rating_mode === 'emoji') {
    const emojis = ['😡', '😐', '😀']
    return (
      <div className="flex justify-center gap-3">
        {settings.rating_options
          .filter((option) => option.enabled)
          .map((option, index) => (
            <div
              key={option.key}
              className={cn(
                'flex h-14 w-14 items-center justify-center rounded-md border border-border text-2xl',
                option.key === selected.key && 'border-foreground bg-muted',
              )}
            >
              {emojis[index] ?? '😀'}
            </div>
          ))}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {settings.rating_options
        .filter((option) => option.enabled)
        .map((option) => (
          <span
            key={option.key}
            className={cn(
              'rounded-md border border-border px-3 py-1.5 text-sm text-foreground',
              option.key === selected.key && 'border-foreground bg-muted',
            )}
          >
            {option.name}
          </span>
        ))}
    </div>
  )
}

function ResolutionPreview({ locale }: { locale: Locale }) {
  const [value, setValue] = useState<'resolved' | 'unresolved'>('resolved')

  const options = [
    { value: 'resolved' as const, label: text(locale, 'resolved') },
    { value: 'unresolved' as const, label: text(locale, 'unresolved') },
  ]

  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <span className="text-sm font-medium text-foreground">{text(locale, 'resolution')}</span>
      <div className="flex justify-center gap-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setValue(option.value)}
            className={cn(
              'rounded-full px-4 py-1.5 text-sm font-medium transition-colors',
              value === option.value
                ? 'bg-primary text-primary-foreground'
                : 'border border-border bg-white text-foreground hover:bg-accent',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function PreviewSection({
  kind,
  settings,
  locale,
}: {
  kind: SatisfactionSurveyType
  settings: ServiceSatisfactionSettings | ProductSatisfactionSettings
  locale: Locale
}) {
  if (!settings.enabled) return null
  const selected = firstActiveOption(settings)
  const showRemark = Boolean(settings.remark_enabled && selected && selected.remark_requirement !== 'hidden')

  return (
    <div className="flex flex-col gap-4 border-b border-border py-5 last:border-b-0">
      <div className="text-center">
        <h3 className="text-sm font-semibold text-foreground">{settings.section_title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{settings.popup_title}</p>
      </div>
      {kind === 'service' && (settings as ServiceSatisfactionSettings).show_resolution && (
        <ResolutionPreview locale={locale} />
      )}
      <RatingPreview settings={settings} />
      {selected && selected.labels.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {selected.labels.map((label) => (
            <span key={label} className="rounded-xl bg-muted px-2.5 py-1 text-xs font-medium text-foreground/80">
              {label}
            </span>
          ))}
        </div>
      )}
      {showRemark && (
        <textarea
          disabled
          placeholder={settings.remark_placeholder}
          className="min-h-20 resize-none rounded-md border border-border bg-white p-3 text-sm placeholder:text-muted-foreground"
        />
      )}
    </div>
  )
}

function SatisfactionPreview({ draft, locale }: { draft: DraftConfig; locale: Locale }) {
  const hasAny = draft.service.enabled || draft.product.enabled
  return (
    <aside className="h-fit rounded-md border border-border bg-background p-4 xl:sticky xl:top-20">
      {hasAny ? (
        <>
          <PreviewSection kind="service" settings={draft.service} locale={locale} />
          <PreviewSection kind="product" settings={draft.product} locale={locale} />
          <button
            type="button"
            disabled
            className="mt-5 h-10 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground opacity-80"
          >
            {text(locale, 'preview.submit')}
          </button>
        </>
      ) : (
        <p className="py-12 text-center text-sm text-muted-foreground">{text(locale, 'preview.empty')}</p>
      )}
    </aside>
  )
}

export function SatisfactionSurveyForm() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isPending, isError, refetch } = useSatisfactionSurveyConfig()
  const saveMut = useSaveSatisfactionSurveyConfig()
  const [draft, setDraft] = useState<DraftConfig | null>(null)
  const [savedSnapshot, setSavedSnapshot] = useState('')
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (!data) return
    const next = stripMeta(data)
    setDraft(next)
    setSavedSnapshot(serializeDraft(next))
  }, [data])

  const currentSnapshot = useMemo(() => (draft ? serializeDraft(draft) : ''), [draft])
  const isDirty = Boolean(draft && currentSnapshot !== savedSnapshot)

  const showToast = (type: 'success' | 'error', message: string) => {
    setToast({ type, text: message })
    setTimeout(() => setToast(null), 3000)
  }

  const updateDraft = (patch: Partial<DraftConfig>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current))
  }

  const updateType = (
    kind: SatisfactionSurveyType,
    next: ServiceSatisfactionSettings | ProductSatisfactionSettings,
  ) => {
    setDraft((current) => (current ? ({ ...current, [kind]: next } as DraftConfig) : current))
  }

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(text(locale, 'leaveConfirm'))) {
      return
    }
    router.push('/online-service/conversation-settings')
  }

  const handleSave = async () => {
    if (!draft) return
    const error = validateDraft(draft, locale)
    if (error) {
      showToast('error', error)
      return
    }
    try {
      const saved = await saveMut.mutateAsync(draft)
      const next = stripMeta(saved)
      setDraft(next)
      setSavedSnapshot(serializeDraft(next))
      showToast('success', text(locale, 'saveSuccess'))
    } catch {
      showToast('error', text(locale, 'saveFailed'))
    }
  }

  if (!draft) {
    return (
      <div className="-m-8 flex flex-col">
        <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
          <button
            type="button"
            onClick={() => router.push('/online-service/conversation-settings')}
            className="flex min-w-0 items-center gap-2 text-left"
          >
            <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
            <span className="truncate text-base font-semibold text-foreground">{text(locale, 'formTitle')}</span>
          </button>
        </div>
        <div className="flex flex-col gap-4 p-8">
          {isPending ? (
            <div className="flex flex-col gap-4">
              <div className="h-10 w-64 animate-pulse rounded-md bg-muted" />
              <div className="h-40 animate-pulse rounded-md bg-muted" />
              <div className="h-40 animate-pulse rounded-md bg-muted" />
            </div>
          ) : isError ? (
            <>
              <p className="text-sm text-muted-foreground">{text(locale, 'summary.loadFailed')}</p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="inline-flex h-9 items-center rounded-md border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
                >
                  {t('vc.retry', locale)}
                </button>
                <button
                  type="button"
                  onClick={() => router.push('/online-service/conversation-settings')}
                  className="inline-flex h-9 items-center rounded-md px-4 text-sm font-medium text-muted-foreground hover:bg-accent"
                >
                  {text(locale, 'back')}
                </button>
              </div>
            </>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
        <button type="button" onClick={goBack} className="flex min-w-0 items-center gap-2 text-left">
          <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
          <span className="truncate text-base font-semibold text-foreground">{text(locale, 'formTitle')}</span>
        </button>
        <button
          type="button"
          disabled={!isDirty || saveMut.isPending}
          onClick={handleSave}
          className="inline-flex h-9 shrink-0 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/80 disabled:opacity-40"
        >
          {saveMut.isPending ? text(locale, 'saving') : text(locale, 'save')}
        </button>
      </div>

      {toast && (
        <div
          className={cn(
            'mx-8 mt-4 rounded-md px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700',
          )}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-8 p-8 xl:flex-row xl:items-start">
        <div className="flex w-full max-w-[780px] shrink-0 flex-col gap-7">
          <section className="flex flex-col gap-4">
            <h2 className="text-base font-semibold text-foreground">{text(locale, 'basic')}</h2>
            <div className="flex flex-col gap-2">
              <FieldLabel required>{text(locale, 'name')}</FieldLabel>
              <TextInput
                value={draft.name}
                onChange={(name) => updateDraft({ name })}
                placeholder={text(locale, 'name.placeholder')}
              />
            </div>
            <div className="flex items-center justify-between gap-4">
              <FieldLabel>{text(locale, 'enabled')}</FieldLabel>
              <Switch checked={draft.enabled} onCheckedChange={(enabled) => updateDraft({ enabled })} />
            </div>
          </section>

          <section className="border-t border-border pt-7">
            <h2 className="text-base font-semibold text-foreground">{text(locale, 'trigger')}</h2>
            <div className="mt-4 flex flex-col gap-4">
              {SATISFACTION_TRIGGER_MODES.map((mode) => (
                <label key={mode} className="flex items-center gap-3 text-sm text-foreground">
                  <Checkbox
                    checked={draft.triggers[mode]}
                    onCheckedChange={(checked) =>
                      updateDraft({
                        triggers: { ...draft.triggers, [mode]: checked === true },
                      })
                    }
                  />
                  {text(locale, `trigger.mode.${mode}`)}
                </label>
              ))}
              <div className="flex items-center justify-between gap-4">
                <FieldLabel>{text(locale, 'limitOnce')}</FieldLabel>
                <Switch
                  checked={draft.triggers.limit_one_response_per_type}
                  onCheckedChange={(limit_one_response_per_type) =>
                    updateDraft({
                      triggers: { ...draft.triggers, limit_one_response_per_type },
                    })
                  }
                />
              </div>
            </div>
          </section>

          <TypeSettingsEditor
            kind="service"
            settings={draft.service}
            locale={locale}
            onChange={(next) => updateType('service', next)}
          />
          <TypeSettingsEditor
            kind="product"
            settings={draft.product}
            locale={locale}
            onChange={(next) => updateType('product', next)}
          />
        </div>

        <div className="w-full shrink-0 xl:ml-auto xl:w-[360px]">
          <SatisfactionPreview draft={draft} locale={locale} />
        </div>
      </div>
    </div>
  )
}
