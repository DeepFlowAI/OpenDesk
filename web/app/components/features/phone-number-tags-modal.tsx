'use client'

import { useEffect, useMemo, useState, type ClipboardEvent, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import type { OutboundTimeSlot, PhoneCallType, TenantPhoneNumber } from '@/models/tenant-phone-number'

const MAX_TAGS = 20
const MAX_TAG_LENGTH = 32

function CallTypeBadge({ type, locale }: { type: PhoneCallType; locale: 'zh' | 'en' }) {
  const label = type === 'inbound' ? t('pn.type.inbound', locale) : t('pn.type.outbound', locale)
  const className =
    type === 'inbound' ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700'
  return (
    <span className={cn('inline-flex rounded-md px-2 py-0.5 text-xs font-medium', className)}>
      {label}
    </span>
  )
}

function TagInput({
  tags,
  onChange,
  placeholder,
  disabled,
  error,
}: {
  tags: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  disabled?: boolean
  error?: string | null
}) {
  const [inputValue, setInputValue] = useState('')

  const addTags = (rawValues: string[]) => {
    const next = [...tags]
    const seen = new Set(next.map((tag) => tag.toLowerCase()))
    for (const raw of rawValues) {
      const value = raw.trim().slice(0, MAX_TAG_LENGTH)
      if (!value) continue
      const key = value.toLowerCase()
      if (seen.has(key) || next.length >= MAX_TAGS) continue
      seen.add(key)
      next.push(value)
    }
    onChange(next)
    setInputValue('')
  }

  const addLabel = (raw: string) => addTags([raw])

  const removeLabel = (index: number) => {
    onChange(tags.filter((_, tagIndex) => tagIndex !== index))
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      addLabel(inputValue)
      return
    }
    if (event.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeLabel(tags.length - 1)
    }
  }

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const text = event.clipboardData.getData('text')
    if (!text.includes(',')) return
    event.preventDefault()
    addTags(text.split(','))
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div
        className={cn(
          'flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-border bg-white px-2 py-1 focus-within:outline-none focus-within:ring-1 focus-within:ring-ring',
          disabled && 'bg-muted',
        )}
      >
        {tags.map((label, index) => (
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
          onChange={(event) => setInputValue(event.target.value.slice(0, MAX_TAG_LENGTH))}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          disabled={disabled || tags.length >= MAX_TAGS}
          placeholder={tags.length === 0 ? placeholder : undefined}
          className="min-w-[72px] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:text-muted-foreground"
        />
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}

export function PhoneNumberTagsModal({
  item,
  open,
  loading,
  saving,
  onClose,
  onSave,
}: {
  item: TenantPhoneNumber | null
  open: boolean
  loading: boolean
  saving: boolean
  onClose: () => void
  onSave: (tags: string[]) => Promise<void>
}) {
  const { locale } = useLocaleStore()
  const [tags, setTags] = useState<string[]>([])
  const [tagError, setTagError] = useState<string | null>(null)

  useEffect(() => {
    if (open && item) {
      setTags(item.tags ?? [])
      setTagError(null)
    }
  }, [open, item])

  const unchanged = useMemo(() => {
    if (!item) return true
    const current = item.tags ?? []
    return current.length === tags.length && current.every((value, index) => value === tags[index])
  }, [item, tags])

  if (!open || !item) return null

  const validateTagInput = (nextTags: string[]) => {
    for (const tag of nextTags) {
      if (tag.trim().length === 0) {
        return t('pn.tags.error.empty', locale)
      }
      if (tag.length > MAX_TAG_LENGTH) {
        return t('pn.tags.error.maxLength', locale)
      }
    }
    const lowered = nextTags.map((tag) => tag.toLowerCase())
    if (new Set(lowered).size !== lowered.length) {
      return t('pn.tags.error.duplicate', locale)
    }
    if (nextTags.length > MAX_TAGS) {
      return t('pn.tags.error.maxCount', locale)
    }
    return null
  }

  const handleSave = async () => {
    const error = validateTagInput(tags)
    if (error) {
      setTagError(error)
      return
    }
    setTagError(null)
    try {
      await onSave(tags)
    } catch (err) {
      if (err instanceof Error && err.message) {
        setTagError(err.message)
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[480px] rounded-xl bg-white p-6 shadow-lg">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold text-foreground">{t('pn.modal.title', locale)}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label={t('pn.modal.close', locale)}
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-6 space-y-4">
          <div>
            <div className="text-sm font-medium text-foreground">{t('pn.col.number', locale)}</div>
            <div className="mt-1 text-sm text-foreground/80">{item.phone_number}</div>
          </div>

          <div>
            <div className="text-sm font-medium text-foreground">{t('pn.col.type', locale)}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {item.call_types.length > 0 ? (
                item.call_types.map((type) => (
                  <CallTypeBadge key={type} type={type} locale={locale} />
                ))
              ) : (
                <span className="text-sm text-muted-foreground">—</span>
              )}
            </div>
          </div>

          <div>
            <div className="text-sm font-medium text-foreground">
              {t('pn.col.outboundTime', locale)}
            </div>
            <div className="mt-1">
              <OutboundTimeSlotsDisplay slots={item.outbound_time_slots} />
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-medium text-foreground">{t('pn.col.tags', locale)}</div>
            {loading ? (
              <p className="text-sm text-muted-foreground">{t('pn.loading', locale)}</p>
            ) : (
              <TagInput
                tags={tags}
                onChange={(next) => {
                  setTags(next)
                  setTagError(validateTagInput(next))
                }}
                placeholder={t('pn.tags.placeholder', locale)}
                disabled={saving}
                error={tagError}
              />
            )}
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('pn.modal.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || loading || unchanged}
            className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? t('pn.modal.saving', locale) : t('pn.modal.save', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

export function OutboundTimeSlotsDisplay({ slots }: { slots: OutboundTimeSlot[] }) {
  if (!slots.length) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-col gap-0.5 text-sm text-foreground/80">
      {slots.map((slot, index) => (
        <span key={`${slot.start}-${slot.end}-${index}`}>
          {slot.start}-{slot.end}
        </span>
      ))}
    </div>
  )
}

export function CallTypeBadges({
  types,
  locale,
}: {
  types: PhoneCallType[]
  locale: 'zh' | 'en'
}) {
  if (types.length === 0) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-2">
      {types.map((type) => (
        <CallTypeBadge key={type} type={type} locale={locale} />
      ))}
    </div>
  )
}

export function PhoneNumberTagList({ tags }: { tags: string[] }) {
  if (!tags.length) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex rounded-md bg-muted px-2 py-0.5 text-xs text-foreground"
        >
          {tag}
        </span>
      ))}
    </div>
  )
}
