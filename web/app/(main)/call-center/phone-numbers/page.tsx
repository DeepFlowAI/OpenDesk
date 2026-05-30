'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { HTTPError } from 'ky'
import { IconPencil, IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  CallTypeBadges,
  OutboundTimeSlotsDisplay,
  PhoneNumberTagList,
  PhoneNumberTagsModal,
} from '@/app/components/features/phone-number-tags-modal'
import {
  useTenantPhoneNumber,
  useTenantPhoneNumbers,
  useUpdateTenantPhoneNumberTags,
} from '@/service/use-tenant-phone-numbers'
import type { TenantPhoneNumber } from '@/models/tenant-phone-number'

const PER_PAGE_OPTIONS = [20, 50, 100] as const

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

export default function PhoneNumbersPage() {
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState<number>(20)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [editTarget, setEditTarget] = useState<TenantPhoneNumber | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data, isLoading, isError, refetch } = useTenantPhoneNumbers({
    page,
    per_page: perPage,
    q: query || undefined,
  })
  const detailQuery = useTenantPhoneNumber(editTarget?.id ?? '', !!editTarget)
  const updateTags = useUpdateTenantPhoneNumberTags()

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 0

  const showToast = useCallback((type: 'success' | 'error', text: string) => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current)
    }
    setToast({ type, text })
    toastTimerRef.current = setTimeout(() => setToast(null), 3000)
  }, [])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current)
      }
    }
  }, [])

  const applySearch = () => {
    setPage(1)
    setQuery(searchInput.trim())
  }

  const handleSaveTags = async (tags: string[]) => {
    if (!editTarget) return
    try {
      await updateTags.mutateAsync({ id: editTarget.id, data: { tags } })
      setEditTarget(null)
      showToast('success', t('pn.saveSuccess', locale))
    } catch (error) {
      const message = await getErrorMessage(error, t('pn.saveFailed', locale))
      showToast('error', message)
      throw new Error(message)
    }
  }

  const emptyMessage =
    query.trim().length > 0 ? t('pn.emptySearch', locale) : t('pn.empty', locale)

  return (
    <div className="flex flex-col gap-6">
      {toast ? (
        <div
          className={`rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      ) : null}

      <h1 className="text-xl font-semibold text-foreground">{t('pn.title', locale)}</h1>

      <div className="flex items-center gap-3">
        <div className="relative max-w-md flex-1">
          <IconSearch
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') applySearch()
            }}
            onBlur={applySearch}
            placeholder={t('pn.search.placeholder', locale)}
            className="h-9 w-full rounded-lg border border-border bg-white pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('pn.loading', locale)}</p>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <p className="text-sm text-muted-foreground">{t('pn.loadFailed', locale)}</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {t('pn.retry', locale)}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="flex h-12 items-center bg-muted px-6 text-sm font-semibold text-foreground">
            <div className="flex-[1.2]">{t('pn.col.number', locale)}</div>
            <div className="w-32">{t('pn.col.type', locale)}</div>
            <div className="w-40">{t('pn.col.outboundTime', locale)}</div>
            <div className="flex-1">{t('pn.col.tags', locale)}</div>
            <div className="w-24 text-right">{t('pn.col.actions', locale)}</div>
          </div>
          {items.map((item) => (
            <div
              key={item.id}
              className="flex min-h-14 items-center border-t border-border px-6 py-3 text-sm text-foreground"
            >
              <div className="flex-[1.2] font-medium">{item.phone_number}</div>
              <div className="w-32">
                <CallTypeBadges types={item.call_types} locale={locale} />
              </div>
              <div className="w-40">
                <OutboundTimeSlotsDisplay slots={item.outbound_time_slots ?? []} />
              </div>
              <div className="flex-1">
                <PhoneNumberTagList tags={item.tags} />
              </div>
              <div className="flex w-24 justify-end">
                <button
                  type="button"
                  onClick={() => setEditTarget(item)}
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary/80"
                >
                  <IconPencil size={16} />
                  {t('pn.action.edit', locale)}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && !isError && total > 0 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>{t('pn.pagination.total', locale, { total: String(total) })}</span>
          <div className="flex items-center gap-3">
            <select
              value={perPage}
              onChange={(event) => {
                setPerPage(Number(event.target.value))
                setPage(1)
              }}
              className="h-9 rounded-lg border border-border bg-white px-2 text-sm text-foreground"
            >
              {PER_PAGE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {t('pn.pagination.perPage', locale, { size: String(size) })}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((current) => Math.max(1, current - 1))}
                className="h-9 rounded-lg border border-border px-3 disabled:opacity-50"
              >
                {t('pn.pagination.prev', locale)}
              </button>
              <span>
                {page} / {Math.max(pages, 1)}
              </span>
              <button
                type="button"
                disabled={pages === 0 || page >= pages}
                onClick={() => setPage((current) => current + 1)}
                className="h-9 rounded-lg border border-border px-3 disabled:opacity-50"
              >
                {t('pn.pagination.next', locale)}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <PhoneNumberTagsModal
        item={detailQuery.data ?? editTarget}
        open={!!editTarget}
        loading={detailQuery.isLoading}
        saving={updateTags.isPending}
        onClose={() => setEditTarget(null)}
        onSave={handleSaveTags}
      />
    </div>
  )
}
