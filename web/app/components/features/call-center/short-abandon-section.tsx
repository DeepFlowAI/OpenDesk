'use client'

import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type ShortAbandonSectionProps = {
  locale: Locale
  value: string
  onChange: (value: string) => void
  onSave: () => void
  saving: boolean
  dirty: boolean
  valid: boolean
  parsed: number
}

export function ShortAbandonSection({
  locale,
  value,
  onChange,
  onSave,
  saving,
  dirty,
  valid,
  parsed,
}: ShortAbandonSectionProps) {
  const invalid = !valid
  const hint = invalid
    ? t('cs.shortAbandon.hintInvalid', locale)
    : t('cs.shortAbandon.hintRange', locale, { n: parsed })

  return (
    <section className="flex max-w-[640px] flex-col gap-3">
      <h2 className="text-sm font-medium text-foreground">
        {t('cs.shortAbandon', locale)}
      </h2>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {t('cs.shortAbandon.desc', locale)}
      </p>
      <label className="grid max-w-[240px] gap-1.5">
        <span className="text-sm font-medium text-foreground">
          <span className="mr-0.5 text-destructive">*</span>
          {t('cs.shortAbandon.label', locale)}
        </span>
        <div
          className={`flex h-10 items-center rounded-md border bg-background px-3 text-sm ${
            invalid ? 'border-destructive' : 'border-border'
          }`}
        >
          <input
            type="text"
            inputMode="numeric"
            value={value}
            disabled={saving}
            onChange={(event) => onChange(event.target.value)}
            className="h-full w-full flex-1 bg-transparent tabular-nums outline-none disabled:cursor-not-allowed"
          />
          <span className="text-sm text-muted-foreground">
            {t('cs.shortAbandon.unit', locale)}
          </span>
        </div>
      </label>
      <p
        className={`text-sm leading-relaxed ${
          invalid ? 'text-destructive' : 'text-muted-foreground'
        }`}
      >
        {hint}
      </p>
      <button
        type="button"
        onClick={onSave}
        disabled={saving || !dirty || invalid}
        className="flex h-10 w-fit items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
      >
        {saving ? t('cs.saving', locale) : t('cs.save', locale)}
      </button>
    </section>
  )
}
