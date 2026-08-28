'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { IconArrowLeft, IconRefresh } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { WorkspaceDashboardCard } from './workspace-dashboard-card'
import { WorkspaceDashboardFilters } from './workspace-dashboard-filters'
import type { ComponentPreview, DashboardRunResult } from '@/models/custom-dashboard'
import {
  cancelCustomDashboardPageRun,
  runWorkspaceCustomDashboardComponent,
  useWorkspaceCustomDashboard,
} from '@/service/use-custom-dashboards'
import { useUnifiedFields } from '@/service/use-field-definitions'
import {
  buildDashboardDrilldownConditions,
  buildDashboardDrilldownUrl,
  defaultDashboardFilterValues,
  parseDashboardFilterValues,
  sanitizeDashboardFilterValues,
} from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function WorkspaceDashboardView({ id }: { id: number }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const query = useWorkspaceCustomDashboard(id)
  const fieldsQuery = useUnifiedFields({ domain: 'ticket', locale, include_metadata: true })
  const [filterValues, setFilterValues] = useState<Record<string, unknown> | null>(null)
  const [previews, setPreviews] = useState<Record<string, ComponentPreview>>({})
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const pageRunId = useRef<string | null>(null)
  const generation = useRef(0)
  const initializedRevision = useRef<number | null>(null)
  const detail = query.data
  const fields = useMemo(() => fieldsQuery.data?.items ?? [], [fieldsQuery.data?.items])

  useEffect(() => {
    if (!detail || !fieldsQuery.data || initializedRevision.current === detail.revision) return
    initializedRevision.current = detail.revision
    const defaults = defaultDashboardFilterValues(detail.filters, detail.timezone)
    const parsed = parseDashboardFilterValues(searchParams.get('filterValues'), detail.filters)
    const sanitized = sanitizeDashboardFilterValues({ ...defaults, ...parsed.values }, detail.filters, fieldsQuery.data.items)
    if (parsed.invalid || sanitized.invalid) toast.warning(t('ws.cd.invalidFilters', locale))
    setFilterValues(sanitized.values)
  }, [detail, fieldsQuery.data, locale, searchParams])

  useEffect(() => {
    if (!filterValues) return
    const params = new URLSearchParams(searchParams.toString())
    params.set('filterValues', JSON.stringify(filterValues))
    const next = JSON.stringify(filterValues)
    if (searchParams.get('filterValues') !== next) router.replace(`?${params.toString()}`, { scroll: false })
  }, [filterValues, router, searchParams])

  const runBatch = useCallback(async (bypassCache = false) => {
    if (!detail || !filterValues) return
    const currentFilterValues = filterValues
    const currentGeneration = generation.current + 1
    generation.current = currentGeneration
    if (pageRunId.current) void cancelCustomDashboardPageRun(pageRunId.current)
    const currentPageRunId = crypto.randomUUID()
    pageRunId.current = currentPageRunId
    setPreviews(Object.fromEntries(detail.components.map((component) => [component.id, { status: 'running' as const }])))
    const queue = [...detail.components]
    let cursor = 0
    const timeout = window.setTimeout(() => {
      if (generation.current !== currentGeneration) return
      generation.current += 1
      void cancelCustomDashboardPageRun(currentPageRunId)
      setPreviews((current) => Object.fromEntries(Object.entries(current).map(([componentId, preview]) => [componentId, preview.status === 'running' ? { status: 'failed', response: failureResponse(componentId, t('ws.cd.pageTimeout', locale)) } : preview])))
    }, 30_000)

    async function worker() {
      while (cursor < queue.length && generation.current === currentGeneration) {
        const component = queue[cursor]
        cursor += 1
        const requestId = crypto.randomUUID()
        try {
          const response = await runWorkspaceCustomDashboardComponent(id, { request_id: requestId, page_run_id: currentPageRunId, component_id: component.id, filter_values: currentFilterValues, bypass_cache: bypassCache })
          if (generation.current === currentGeneration) setPreviews((current) => ({ ...current, [component.id]: { status: response.status, response } }))
        } catch {
          if (generation.current === currentGeneration) setPreviews((current) => ({ ...current, [component.id]: { status: 'failed', response: failureResponse(requestId, t('ws.cd.runFailed', locale)) } }))
        }
      }
    }

    await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
    window.clearTimeout(timeout)
    if (generation.current === currentGeneration) setLastRefresh(new Date())
  }, [detail, filterValues, id, locale])

  useEffect(() => {
    if (!detail || !filterValues) return
    const timeout = window.setTimeout(() => void runBatch(false), 300)
    return () => window.clearTimeout(timeout)
  }, [detail, filterValues, runBatch])

  useEffect(() => () => {
    generation.current += 1
    if (pageRunId.current) void cancelCustomDashboardPageRun(pageRunId.current)
  }, [])

  async function retry(componentId: string) {
    if (!filterValues) return
    const currentPageRunId = pageRunId.current ?? crypto.randomUUID()
    pageRunId.current = currentPageRunId
    const requestId = crypto.randomUUID()
    setPreviews((current) => ({ ...current, [componentId]: { status: 'running' } }))
    try {
      const response = await runWorkspaceCustomDashboardComponent(id, { request_id: requestId, page_run_id: currentPageRunId, component_id: componentId, filter_values: filterValues, bypass_cache: true })
      setPreviews((current) => ({ ...current, [componentId]: { status: response.status, response } }))
    } catch {
      setPreviews((current) => ({ ...current, [componentId]: { status: 'failed', response: failureResponse(requestId, t('ws.cd.runFailed', locale)) } }))
    }
  }

  if (query.isError) return <div className="grid h-full place-items-center text-sm text-destructive">{t('ws.cd.notFound', locale)}</div>
  if (!detail || !filterValues) return <div className="grid h-full place-items-center text-sm text-muted-foreground">{t('cd.loading', locale)}</div>
  const maxRow = Math.max(16, ...detail.components.map((component) => component.y + component.h + 2))

  return (
    <div className="h-full overflow-y-auto bg-background p-7">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3"><Button variant="ghost" size="icon" onClick={() => router.push('/workspace/records/dashboards')} aria-label={t('cd.back', locale)}><IconArrowLeft /></Button><div><h1 className="text-xl font-semibold text-foreground">{detail.name}</h1>{detail.description && <p className="mt-1 text-sm text-muted-foreground">{detail.description}</p>}</div></div>
        <div className="flex items-center gap-3"><span className="text-xs text-muted-foreground">{lastRefresh ? t('ws.cd.lastRefresh', locale, { time: lastRefresh.toLocaleTimeString(locale) }) : t('ws.cd.notRefreshed', locale)}</span><Button variant="outline" onClick={() => void runBatch(true)}><IconRefresh />{t('ws.cd.refresh', locale)}</Button></div>
      </div>
      <div className="mt-5"><WorkspaceDashboardFilters filters={detail.filters} fields={fields} values={filterValues} onChange={setFilterValues} timezone={detail.timezone} /></div>
      {detail.components.length === 0 ? <div className="mt-5 rounded-xl border border-dashed border-border py-24 text-center text-sm text-muted-foreground">{t('ws.cd.noComponents', locale)}</div> : <div className="mt-5 grid grid-cols-12 auto-rows-[32px] gap-3" style={{ minHeight: maxRow * 32 }}>{detail.components.map((component) => <WorkspaceDashboardCard key={component.id} component={component} preview={previews[component.id]} onRetry={() => void retry(component.id)} onDrilldown={(output) => { const conditions = buildDashboardDrilldownConditions(output, detail.filters, filterValues, fields); if (conditions.length === 0) { toast.warning(t('ws.cd.invalidDrilldown', locale)); return } router.push(buildDashboardDrilldownUrl(id, conditions, filterValues)) }} />)}</div>}
    </div>
  )
}

function failureResponse(requestId: string, message: string): DashboardRunResult {
  return { request_id: requestId, status: 'failed', result: null, cached: false, error_code: 'request_failed', message, error_line: null, logs: null, logs_truncated: false, query_count: 0, completed_at: new Date().toISOString() }
}
