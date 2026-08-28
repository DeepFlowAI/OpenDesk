'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useState } from 'react'
import { IconSearch, IconX } from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSmsTemplate, useSmsTemplates } from '@/service/use-sms'
import type { SmsTemplateStatus, SmsTemplateType } from '@/models/sms'

const PER_PAGE = 20

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function TypeTag({ type, locale }: { type: SmsTemplateType; locale: Locale }) {
  return (
    <span className="rounded-md bg-sky-50 px-2 py-1 text-[11px] text-sky-700 dark:bg-sky-950 dark:text-sky-300">
      {t(`sms.type.${type}`, locale)}
    </span>
  )
}

function StatusTag({ status, locale }: { status: SmsTemplateStatus; locale: Locale }) {
  const tone =
    status === 'available'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300'
      : 'bg-muted text-muted-foreground'
  return (
    <span className={`rounded-md px-2 py-1 text-[11px] ${tone}`}>
      {t(`sms.status.${status}`, locale)}
    </span>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{children}</div>
    </div>
  )
}

export default function SmsTemplatesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()

  const q = searchParams.get('q') ?? ''
  const page = Number(searchParams.get('page') ?? '1') || 1

  const [searchInput, setSearchInput] = useState(q)
  const [detailId, setDetailId] = useState<number | null>(null)

  const syncParams = useCallback(
    (next: { q?: string; page?: number }) => {
      const params = new URLSearchParams(searchParams.toString())
      const apply = (key: string, value?: string | number) => {
        if (value === undefined || value === '' || value === null) params.delete(key)
        else params.set(key, String(value))
      }
      if ('q' in next) apply('q', next.q)
      if ('page' in next) apply('page', next.page && next.page > 1 ? next.page : undefined)
      const qs = params.toString()
      router.replace(qs ? `/call-center/sms?${qs}` : '/call-center/sms')
    },
    [router, searchParams],
  )

  const { data, isLoading, isError, refetch } = useSmsTemplates({
    page,
    per_page: PER_PAGE,
    q: q || undefined,
  })
  const detailQuery = useSmsTemplate(detailId)

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0
  const detail = detailQuery.data

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border px-6 py-4">
        <h1 className="text-xl font-semibold text-foreground">{t('sms.title', locale)}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('sms.subtitle', locale)}</p>
      </header>

      <div className="shrink-0 border-b border-border px-6 py-3">
        <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') syncParams({ q: searchInput.trim(), page: 1 })
            }}
            onBlur={() => {
              if (searchInput.trim() !== q) syncParams({ q: searchInput.trim(), page: 1 })
            }}
            placeholder={t('sms.searchPlaceholder', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <main className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('sms.loading', locale)}</p>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16">
            <p className="text-sm text-muted-foreground">{t('sms.loadFailed', locale)}</p>
            <button
              type="button"
              onClick={() => refetch()}
              className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
            >
              {t('sms.retry', locale)}
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-[420px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20">
            <p className="text-sm text-muted-foreground">{t('sms.empty', locale)}</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('sms.col.name', locale)}</th>
                  <th className="px-4 py-3 font-medium">{t('sms.col.signName', locale)}</th>
                  <th className="px-4 py-3 font-medium">{t('sms.col.type', locale)}</th>
                  <th className="px-4 py-3 font-medium">{t('sms.col.variables', locale)}</th>
                  <th className="px-4 py-3 font-medium">{t('sms.col.status', locale)}</th>
                  <th className="px-4 py-3 font-medium">{t('sms.col.updatedAt', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr
                    key={row.id}
                    className="cursor-pointer border-t border-border hover:bg-muted/30"
                    onClick={() => setDetailId(row.id)}
                  >
                    <td className="px-4 py-3 font-medium">{row.name}</td>
                    <td className="px-4 py-3">{row.sign_name}</td>
                    <td className="px-4 py-3">
                      <TypeTag type={row.type} locale={locale} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {row.variables.length
                        ? row.variables.map((variable) => variable.label).join('、')
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusTag status={row.status} locale={locale} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDateTime(row.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && !isError && total > 0 ? (
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>{t('sms.pagination.total', locale, { total: String(total) })}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => syncParams({ page: page - 1 })}
                className="h-8 rounded-lg border border-border px-3 disabled:opacity-50"
              >
                {t('sms.pagination.prev', locale)}
              </button>
              <span>
                {page} / {Math.max(pages, 1)}
              </span>
              <button
                type="button"
                disabled={pages === 0 || page >= pages}
                onClick={() => syncParams({ page: page + 1 })}
                className="h-8 rounded-lg border border-border px-3 disabled:opacity-50"
              >
                {t('sms.pagination.next', locale)}
              </button>
            </div>
          </div>
        ) : null}
      </main>

      {detailId !== null ? (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/20"
            onClick={() => setDetailId(null)}
            aria-hidden
          />
          <aside className="absolute inset-y-0 right-0 flex w-[420px] flex-col border-l border-border bg-background shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-base font-semibold">{t('sms.detail.title', locale)}</h2>
              <button
                type="button"
                onClick={() => setDetailId(null)}
                aria-label={t('sms.detail.close', locale)}
                className="text-muted-foreground hover:text-foreground"
              >
                <IconX size={18} />
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4 text-sm">
              {detailQuery.isLoading || !detail ? (
                <p className="text-muted-foreground">{t('sms.loading', locale)}</p>
              ) : (
                <>
                  <Field label={t('sms.col.name', locale)}>{detail.name}</Field>
                  <Field label={t('sms.col.signName', locale)}>{detail.sign_name}</Field>
                  <Field label={t('sms.col.type', locale)}>
                    {t(`sms.type.${detail.type}`, locale)}
                  </Field>
                  <Field label={t('sms.col.status', locale)}>
                    <StatusTag status={detail.status} locale={locale} />
                  </Field>
                  <div>
                    <div className="mb-1.5 text-xs text-muted-foreground">
                      {t('sms.detail.body', locale)}
                    </div>
                    <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 leading-6">
                      {detail.body}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1.5 text-xs text-muted-foreground">
                      {t('sms.detail.variables', locale)}
                    </div>
                    {detail.variables.length === 0 ? (
                      <div className="text-muted-foreground">—</div>
                    ) : (
                      <div className="space-y-2">
                        {detail.variables.map((variable) => (
                          <div
                            key={variable.key}
                            className="rounded-md border border-border px-3 py-2"
                          >
                            <div className="font-medium">
                              {variable.label}
                              {variable.required ? (
                                <span className="ml-1 text-red-500">*</span>
                              ) : null}
                            </div>
                            <div className="mt-0.5 font-mono text-xs text-muted-foreground">{`{${variable.key}}`}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  )
}
