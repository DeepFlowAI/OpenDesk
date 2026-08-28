'use client'

import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useMemo, useState } from 'react'
import { IconEye, IconPlus, IconSearch } from '@tabler/icons-react'
import {
  AutoTaskStatusBadge,
  ExecutionModeBadge,
  ProgressBar,
  SimplePagination,
  TableSkeleton,
  formatAnswerRate,
  formatDateTime,
} from '@/app/components/features/engagement/auto-outbound-task-ui'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import type { AutoOutboundExecutionMode, AutoOutboundTaskStatus } from '@/models/auto-outbound-task'
import { useAutoOutboundTasks } from '@/service/use-auto-outbound-tasks'
import { hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'

const STATUS_VALUES: AutoOutboundTaskStatus[] = ['draft', 'active', 'paused', 'completed', 'archived']
const MODE_VALUES: AutoOutboundExecutionMode[] = ['ivr', 'bot', 'agent']
const PAGE_SIZE = 50

export default function AutoOutboundTasksPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const canCreate = hasPermission(user, 'engagement.auto_outbound_task.create')

  const q = searchParams.get('q') ?? ''
  const status = (searchParams.get('status') ?? '') as '' | AutoOutboundTaskStatus
  const mode = (searchParams.get('mode') ?? '') as '' | AutoOutboundExecutionMode
  const page = Number(searchParams.get('page') ?? '1') || 1

  const [searchInput, setSearchInput] = useState(q)

  const syncParams = useCallback(
    (next: { q?: string; status?: string; mode?: string; page?: number }) => {
      const params = new URLSearchParams(searchParams.toString())
      const apply = (key: string, value?: string | number) => {
        if (value === undefined || value === '' || value === null) params.delete(key)
        else params.set(key, String(value))
      }
      if ('q' in next) apply('q', next.q)
      if ('status' in next) apply('status', next.status)
      if ('mode' in next) apply('mode', next.mode)
      if ('page' in next) apply('page', next.page && next.page > 1 ? next.page : undefined)
      const qs = params.toString()
      router.replace(qs ? `/workspace/engagement/auto-outbound-tasks?${qs}` : '/workspace/engagement/auto-outbound-tasks')
    },
    [router, searchParams],
  )

  const queryParams = useMemo(
    () => ({ page, page_size: PAGE_SIZE, q: q || undefined, status: status || undefined, mode: mode || undefined }),
    [mode, page, q, status],
  )
  const { data, isLoading, isError } = useAutoOutboundTasks(queryParams)
  const hasFilters = Boolean(q || status || mode)

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t('ws.autoOutbound.list.title', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('ws.autoOutbound.list.subtitle', locale)}</p>
        </div>
        {canCreate && (
          <Link
            href="/workspace/engagement/auto-outbound-tasks/new"
            className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          >
            <IconPlus size={16} />
            {t('ws.autoOutbound.list.create', locale)}
          </Link>
        )}
      </header>

      <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3">
        <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') syncParams({ q: searchInput.trim(), page: 1 })
            }}
            onBlur={() => {
              if (searchInput.trim() !== q) syncParams({ q: searchInput.trim(), page: 1 })
            }}
            placeholder={t('ws.autoOutbound.list.searchPlaceholder', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </div>
        <select
          value={status}
          onChange={(e) => syncParams({ status: e.target.value, page: 1 })}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">{t('ws.autoOutbound.list.statusAll', locale)}</option>
          {STATUS_VALUES.map((value) => (
            <option key={value} value={value}>{t(`ws.autoOutbound.status.${value}`, locale)}</option>
          ))}
        </select>
        <select
          value={mode}
          onChange={(e) => syncParams({ mode: e.target.value, page: 1 })}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">{t('ws.autoOutbound.list.modeAll', locale)}</option>
          {MODE_VALUES.map((value) => (
            <option key={value} value={value}>{t(`ws.autoOutbound.mode.${value}`, locale)}</option>
          ))}
        </select>
      </div>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <TableSkeleton />
        ) : isError ? (
          <EmptyState title={t('ws.autoOutbound.list.loadFailed', locale)} />
        ) : (data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title={hasFilters ? t('ws.autoOutbound.list.emptyFiltered', locale) : t('ws.autoOutbound.list.empty', locale)}
            action={
              canCreate && !hasFilters ? (
                <Link
                  href="/workspace/engagement/auto-outbound-tasks/new"
                  className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
                >
                  {t('ws.autoOutbound.list.create', locale)}
                </Link>
              ) : null
            }
          />
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/60 text-left text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.name', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.mode', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.target', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.status', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.owner', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.progress', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.answerRate', locale)}</th>
                    <th className="px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.updatedAt', locale)}</th>
                    <th className="w-20 px-4 py-3 font-medium">{t('ws.autoOutbound.list.col.actions', locale)}</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((task) => {
                    const detailHref = `/workspace/engagement/auto-outbound-tasks/${task.id}${
                      searchParams.toString() ? `?from=${encodeURIComponent(searchParams.toString())}` : ''
                    }`
                    return (
                      <tr key={task.id} className="border-t border-border">
                        <td className="max-w-[220px] truncate px-4 py-3 font-medium">
                          <Link href={detailHref} className="hover:underline">{task.name}</Link>
                        </td>
                        <td className="px-4 py-3">
                          <ExecutionModeBadge mode={task.execution_mode} locale={locale} />
                        </td>
                        <td className="max-w-[180px] truncate px-4 py-3 text-muted-foreground">
                          {task.reception_target_name || '—'}
                        </td>
<td className="px-4 py-3">
  <AutoTaskStatusBadge
    status={task.status}
    outOfWindow={task.out_of_window}
    autoPauseReason={task.auto_pause_reason}
    locale={locale}
  />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{task.owner_name || '—'}</td>
                        <td className="px-4 py-3">
                          <ProgressBar finished={task.finished_targets} total={task.total_targets} />
                        </td>
                        <td className="px-4 py-3">
                          {formatAnswerRate(task.answer_rate, task.answered_count, task.call_count)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{formatDateTime(task.updated_at)}</td>
                        <td className="px-4 py-3">
                          <Link title={t('ws.autoOutbound.list.view', locale)} href={detailHref}>
                            <IconEye size={17} />
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <SimplePagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data?.total ?? 0}
              locale={locale}
              onPageChange={(next) => syncParams({ page: next })}
            />
          </>
        )}
      </main>
    </div>
  )
}
