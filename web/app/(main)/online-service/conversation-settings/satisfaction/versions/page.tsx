'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Eye } from 'lucide-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useSatisfactionSurveyVersion,
  useSatisfactionSurveyVersions,
} from '@/service/use-satisfaction-survey'
import type {
  SatisfactionRatingMode,
  SatisfactionSurveyType,
  SatisfactionTriggerMode,
  SatisfactionTypeSettings,
  SaveSatisfactionSurveyPayload,
} from '@/models/satisfaction-survey'
import { getActiveTriggerModes } from '@/models/satisfaction-survey'

function text(locale: Locale, key: string, params?: Record<string, string | number>) {
  return t(`sat.${key}`, locale, params)
}

function formatDate(iso: string | null, locale: Locale): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (value: number) => String(value).padStart(2, '0')
  if (locale === 'zh') {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  }
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function typeLabel(type: SatisfactionSurveyType, locale: Locale) {
  return type === 'service' ? text(locale, 'service') : text(locale, 'product')
}

function modeLabel(mode: SatisfactionRatingMode | undefined, locale: Locale) {
  if (!mode) return '—'
  return text(locale, `ratingMode.${mode}`)
}

function triggerLabel(mode: SatisfactionTriggerMode, locale: Locale) {
  return text(locale, `trigger.mode.${mode}`)
}

function SnapshotTypeBlock({
  title,
  settings,
  locale,
}: {
  title: string
  settings: SatisfactionTypeSettings
  locale: Locale
}) {
  if (!settings.enabled) return null
  return (
    <section className="border-t border-border pt-4">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
        <div>
          <span className="text-muted-foreground">{text(locale, 'sectionTitle')}</span>
          <p className="mt-1 text-foreground">{settings.section_title}</p>
        </div>
        <div>
          <span className="text-muted-foreground">{text(locale, 'popupTitle')}</span>
          <p className="mt-1 text-foreground">{settings.popup_title}</p>
        </div>
        <div>
          <span className="text-muted-foreground">{text(locale, 'ratingMode')}</span>
          <p className="mt-1 text-foreground">{modeLabel(settings.rating_mode, locale)}</p>
        </div>
        <div>
          <span className="text-muted-foreground">{text(locale, 'tagSelection')}</span>
          <p className="mt-1 text-foreground">{text(locale, `tagSelection.${settings.tag_selection_mode}`)}</p>
        </div>
      </div>
      <div className="mt-4 rounded-md border border-border">
        <div className="grid grid-cols-[1fr_80px_80px_1fr] gap-3 border-b border-border bg-muted px-4 py-2 text-xs font-semibold text-foreground/70">
          <span>{text(locale, 'option.name')}</span>
          <span>{text(locale, 'option.default')}</span>
          <span>{text(locale, 'option.score')}</span>
          <span>{text(locale, 'option.labels')}</span>
        </div>
        {settings.rating_options.map((option) => (
          <div
            key={option.key}
            className="grid grid-cols-[1fr_80px_80px_1fr] gap-3 border-b border-border px-4 py-2 text-sm last:border-b-0"
          >
            <span className={option.enabled ? 'text-foreground' : 'text-muted-foreground'}>{option.name}</span>
            <span>{option.is_default ? text(locale, 'yes') : '—'}</span>
            <span>{option.score}</span>
            <span className="truncate">{option.labels.length ? option.labels.join(', ') : '—'}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function SnapshotModal({
  snapshot,
  loading,
  onClose,
  locale,
}: {
  snapshot: SaveSatisfactionSurveyPayload | null
  loading: boolean
  onClose: () => void
  locale: Locale
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[86vh] w-full max-w-3xl overflow-y-auto rounded-md bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-base font-semibold text-foreground">{text(locale, 'versions.snapshot')}</h2>
          <button
            type="button"
            onClick={onClose}
            className="h-8 rounded-md border border-border px-3 text-sm font-medium text-foreground hover:bg-accent"
          >
            {text(locale, 'close')}
          </button>
        </div>
        {loading || !snapshot ? (
          <p className="mt-6 text-sm text-muted-foreground">{text(locale, 'loading')}</p>
        ) : (
          <div className="mt-5 flex flex-col gap-4">
            <section className="grid gap-3 text-sm md:grid-cols-3">
              <div>
                <span className="text-muted-foreground">{text(locale, 'name')}</span>
                <p className="mt-1 text-foreground">{snapshot.name}</p>
              </div>
              <div>
                <span className="text-muted-foreground">{text(locale, 'enabled')}</span>
                <p className="mt-1 text-foreground">{snapshot.enabled ? text(locale, 'enabled.on') : text(locale, 'enabled.off')}</p>
              </div>
              <div>
                <span className="text-muted-foreground">{text(locale, 'trigger')}</span>
                <p className="mt-1 text-foreground">
                  {getActiveTriggerModes(snapshot.triggers)
                    .map((mode) => text(locale, `trigger.mode.${mode}`))
                    .join(' + ') || '—'}
                </p>
              </div>
            </section>
            <SnapshotTypeBlock title={text(locale, 'service')} settings={snapshot.service} locale={locale} />
            <SnapshotTypeBlock title={text(locale, 'product')} settings={snapshot.product} locale={locale} />
          </div>
        )}
      </div>
    </div>
  )
}

export default function SatisfactionSurveyVersionsPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSatisfactionSurveyVersions({ page: 1, per_page: 50 })
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const { data: snapshot, isLoading: loadingSnapshot } = useSatisfactionSurveyVersion(selectedVersion)

  const rows = data?.items ?? []

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex min-h-14 items-center border-b border-border bg-white px-6 py-2">
        <button
          type="button"
          onClick={() => router.push('/online-service/conversation-settings')}
          className="flex items-center gap-2 text-left"
        >
          <ArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{text(locale, 'versions.title')}</span>
        </button>
      </div>

      <div className="p-8">
        <div className="mb-4 flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            {data?.current_version ? `v${data.current_version} · ${text(locale, 'versions.current')}` : text(locale, 'versions.empty')}
          </p>
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">{text(locale, 'loading')}</p>
        ) : rows.length === 0 ? (
          <div className="flex min-h-60 items-center justify-center text-sm text-muted-foreground">
            {text(locale, 'versions.empty')}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <div className="grid min-w-[960px] grid-cols-[90px_160px_180px_160px_160px_180px_90px] gap-4 border-b border-border bg-muted px-5 py-3 text-sm font-semibold text-foreground/80">
              <span>{text(locale, 'versions.col.version')}</span>
              <span>{text(locale, 'versions.col.types')}</span>
              <span>{text(locale, 'versions.col.modes')}</span>
              <span>{text(locale, 'versions.col.triggers')}</span>
              <span>{text(locale, 'versions.col.operator')}</span>
              <span>{text(locale, 'versions.col.published')}</span>
              <span className="text-center">{text(locale, 'versions.col.actions')}</span>
            </div>
            {rows.map((row) => (
              <div
                key={row.id}
                className="grid min-w-[960px] grid-cols-[90px_160px_180px_160px_160px_180px_90px] items-center gap-4 border-b border-border px-5 py-3 text-sm last:border-b-0"
              >
                <span className="font-medium text-foreground">v{row.version}</span>
                <span className="text-muted-foreground">
                  {row.survey_types.map((type) => typeLabel(type, locale)).join(' + ') || '—'}
                </span>
                <span className="text-muted-foreground">
                  {row.survey_types
                    .map((type) => `${typeLabel(type, locale)}: ${modeLabel(row.rating_modes[type], locale)}`)
                    .join(' / ') || '—'}
                </span>
                <span className="text-muted-foreground">
                  {row.trigger_modes.map((mode) => triggerLabel(mode, locale)).join(' + ') || '—'}
                </span>
                <span className="text-muted-foreground">{row.updated_by_name || '—'}</span>
                <span className="text-muted-foreground">{formatDate(row.published_at, locale)}</span>
                <button
                  type="button"
                  onClick={() => setSelectedVersion(row.version)}
                  className="mx-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-foreground/80 hover:bg-accent"
                  aria-label={text(locale, 'versions.snapshot')}
                >
                  <Eye size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedVersion != null && (
        <SnapshotModal
          snapshot={snapshot?.snapshot ?? null}
          loading={loadingSnapshot}
          onClose={() => setSelectedVersion(null)}
          locale={locale}
        />
      )}
    </div>
  )
}
