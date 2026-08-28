'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconAdjustments,
  IconArrowLeft,
  IconInfoCircle,
  IconPlus,
  IconSettings,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { ComponentDrawer } from './component-drawer'
import { DashboardCanvas } from './dashboard-canvas'
import { DashboardSettingsDrawers, type DashboardSettingsMode } from './dashboard-settings-drawers'
import { WorkspaceDashboardFilters } from './workspace-dashboard-filters'
import type {
  ComponentPreview,
  DashboardComponent,
  DashboardDetail,
  DashboardRunResult,
  DashboardSnapshotPayload,
} from '@/models/custom-dashboard'
import {
  cancelCustomDashboardRun,
  useCustomDashboard,
  usePreviewCustomDashboard,
  usePublishCustomDashboard,
  useUpdateCustomDashboard,
} from '@/service/use-custom-dashboards'
import { useUnifiedFields } from '@/service/use-field-definitions'
import {
  DASHBOARD_MAX_COMPONENTS,
  DEFAULT_DASHBOARD_CODE,
  defaultDashboardFilterValues,
  findAvailablePosition,
  resolveDashboardLayout,
  validateComponent,
  validateDashboardForm,
} from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

function toSnapshot(detail: DashboardDetail): DashboardSnapshotPayload {
  return {
    name: detail.draft.name,
    description: detail.draft.description,
    icon: detail.draft.icon,
    filters: detail.draft.filters,
    components: detail.draft.components,
  }
}

export function DashboardEditor({ id }: { id: number }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const query = useCustomDashboard(id)
  const updateDashboard = useUpdateCustomDashboard()
  const publishDashboard = usePublishCustomDashboard()
  const previewDashboard = usePreviewCustomDashboard(id)
  const fieldsQuery = useUnifiedFields({ domain: 'ticket', locale, include_metadata: true })
  const [detail, setDetail] = useState<DashboardDetail | null>(null)
  const [snapshot, setSnapshot] = useState<DashboardSnapshotPayload | null>(null)
  const [baseline, setBaseline] = useState('')
  const [previews, setPreviews] = useState<Record<string, ComponentPreview>>({})
  const [previewFilterValues, setPreviewFilterValues] = useState<Record<string, unknown>>({})
  const [selected, setSelected] = useState<DashboardComponent | null>(null)
  const [componentDrawerOpen, setComponentDrawerOpen] = useState(false)
  const [settingsMode, setSettingsMode] = useState<DashboardSettingsMode>(null)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [deleteComponent, setDeleteComponent] = useState<DashboardComponent | null>(null)
  const activeRequest = useRef<string | null>(null)
  const snapshotFilters = snapshot?.filters

  useEffect(() => {
    if (!query.data || snapshot) return
    const initial = toSnapshot(query.data)
    setDetail(query.data)
    setSnapshot(initial)
    setBaseline(JSON.stringify(initial))
  }, [query.data, snapshot])

  useEffect(() => {
    if (!snapshotFilters) return
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    const defaults = defaultDashboardFilterValues(snapshotFilters, timezone)
    setPreviewFilterValues((current) => Object.fromEntries(snapshotFilters.flatMap((filter) => {
      const value = current[filter.id] ?? defaults[filter.id]
      return value === undefined ? [] : [[filter.id, value]]
    })))
  }, [snapshotFilters])

  const dirty = snapshot ? JSON.stringify(snapshot) !== baseline : false
  const warningCount = useMemo(() => snapshot?.components.filter((component) => previews[component.id]?.status !== 'success').length ?? 0, [previews, snapshot?.components])

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  const saveDraft = useCallback(async () => {
    if (!snapshot) return null
    const formErrors = validateDashboardForm(snapshot)
    const invalidComponent = snapshot.components.find((component) => validateComponent(component))
    if (Object.keys(formErrors).length > 0 || invalidComponent) {
      toast.error(t('cd.validation.draft', locale))
      return null
    }
    try {
      const saved = await updateDashboard.mutateAsync({ id, data: snapshot })
      const savedSnapshot = toSnapshot(saved)
      setDetail(saved)
      setSnapshot(savedSnapshot)
      setBaseline(JSON.stringify(savedSnapshot))
      toast.success(t('cd.saved', locale))
      return saved
    } catch {
      toast.error(t('cd.actionFailed', locale))
      return null
    }
  }, [id, locale, snapshot, updateDashboard])

  const runPreview = useCallback(async (component: DashboardComponent): Promise<DashboardRunResult> => {
    if (!snapshot) throw new Error('Dashboard is not ready')
    if (activeRequest.current) void cancelCustomDashboardRun(activeRequest.current)
    const requestId = crypto.randomUUID()
    activeRequest.current = requestId
    setPreviews((current) => ({ ...current, [component.id]: { status: 'running' } }))
    try {
      const response = await previewDashboard.mutateAsync({
        request_id: requestId,
        page_run_id: crypto.randomUUID(),
        component_id: component.id,
        component_override: component,
        filter_config_override: snapshot.filters,
        filter_values: previewFilterValues,
      })
      setPreviews((current) => ({ ...current, [component.id]: { status: response.status, response } }))
      return response
    } catch {
      const response: DashboardRunResult = { request_id: requestId, status: 'failed', result: null, cached: false, error_code: 'request_failed', message: t('cd.actionFailed', locale), error_line: null, logs: null, logs_truncated: false, query_count: 0, completed_at: new Date().toISOString() }
      setPreviews((current) => ({ ...current, [component.id]: { status: 'failed', response } }))
      return response
    } finally {
      if (activeRequest.current === requestId) activeRequest.current = null
    }
  }, [locale, previewDashboard, previewFilterValues, snapshot])

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey)) return
      if (event.key.toLowerCase() === 's') { event.preventDefault(); void saveDraft() }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [saveDraft])

  if (query.isError) return <div className="grid h-screen place-items-center text-sm text-destructive">{t('cd.notFound', locale)}</div>
  if (query.isLoading || !snapshot || !detail) return <div className="grid h-screen place-items-center text-sm text-muted-foreground">{t('cd.loading', locale)}</div>

  function addComponent() {
    if (!snapshot || snapshot.components.length >= DASHBOARD_MAX_COMPONENTS) return
    const position = findAvailablePosition(snapshot.components)
    const component: DashboardComponent = { id: crypto.randomUUID(), title: t('cd.defaultComponentTitle', locale), code: DEFAULT_DASHBOARD_CODE, ...position, w: 6, h: 8 }
    setSnapshot({ ...snapshot, components: [...snapshot.components, component] })
    setSelected(component)
    setComponentDrawerOpen(true)
  }

  function copyComponent(component: DashboardComponent) {
    if (!snapshot || snapshot.components.length >= DASHBOARD_MAX_COMPONENTS) return
    const copy = { ...component, id: crypto.randomUUID(), title: `${component.title} ${t('cd.copySuffix', locale)}`, y: component.y + component.h }
    setSnapshot({ ...snapshot, components: resolveDashboardLayout([...snapshot.components, copy], copy.id) })
  }

  async function preparePublish() {
    if (dirty && !(await saveDraft())) return
    setPublishOpen(true)
  }

  async function publish() {
    try {
      const published = await publishDashboard.mutateAsync(id)
      setDetail(published)
      setPublishOpen(false)
      toast.success(t('cd.publishedSuccess', locale))
    } catch {
      toast.error(t('cd.actionFailed', locale))
    }
  }

  function leave() {
    if (dirty) setLeaveOpen(true)
    else router.push('/custom-dashboards')
  }

  return (
    <div className="flex h-screen min-w-[1100px] flex-col overflow-hidden bg-background">
      <header className="z-20 flex h-16 shrink-0 items-center justify-between border-b border-border bg-background px-5">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="icon" onClick={leave} aria-label={t('cd.back', locale)}><IconArrowLeft /></Button>
          <h1 className="truncate text-lg font-semibold">{snapshot.name}</h1>
          <Badge variant={detail.status === 'published' ? 'default' : detail.status === 'disabled' ? 'outline' : 'secondary'}>{t(`cd.status.${detail.status}`, locale)}</Badge>
          <span className="text-xs text-muted-foreground">{dirty ? t('cd.unsaved', locale) : t('cd.savedState', locale)}</span>
        </div>
        <div className="flex items-center gap-2"><Button variant="outline" onClick={() => void saveDraft()} disabled={!dirty || updateDashboard.isPending}>{updateDashboard.isPending ? t('cd.saving', locale) : t('cd.saveDraft', locale)}</Button><Button onClick={() => void preparePublish()} disabled={publishDashboard.isPending}>{t('cd.publish', locale)}</Button></div>
      </header>
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background px-5">
        <Button variant="outline" onClick={addComponent} disabled={snapshot.components.length >= DASHBOARD_MAX_COMPONENTS}><IconPlus />{t('cd.addComponent', locale)}</Button>
        <Button variant="ghost" onClick={() => setSettingsMode('filters')}><IconAdjustments />{t('cd.filters', locale)}<Badge variant="secondary">{snapshot.filters.length}</Badge></Button>
        <Button variant="ghost" onClick={() => setSettingsMode('basic')}><IconSettings />{t('cd.basicSettings', locale)}</Button>
        <Button variant="ghost" onClick={() => setSettingsMode('resources')}><IconInfoCircle />{t('cd.resources', locale)}</Button>
      </div>
      <main className="min-h-0 flex-1 overflow-auto p-5">
        {snapshot.filters.length > 0 && <div className="mb-4"><p className="mb-2 text-xs font-medium text-muted-foreground">{t('cd.filterPreview', locale)}</p><WorkspaceDashboardFilters filters={snapshot.filters} fields={fieldsQuery.data?.items ?? []} values={previewFilterValues} onChange={setPreviewFilterValues} /></div>}
        <DashboardCanvas components={snapshot.components} previews={previews} onChange={(components) => setSnapshot({ ...snapshot, components })} onAdd={addComponent} onEdit={(component) => { setSelected(component); setComponentDrawerOpen(true) }} onCopy={copyComponent} onDelete={setDeleteComponent} />
      </main>

      <ComponentDrawer component={selected} open={componentDrawerOpen} running={previewDashboard.isPending} onOpenChange={setComponentDrawerOpen} onApply={(component) => { setSnapshot({ ...snapshot, components: snapshot.components.map((item) => item.id === component.id ? component : item) }); setSelected(component) }} onPreview={runPreview} />
      <DashboardSettingsDrawers mode={settingsMode} snapshot={snapshot} onChange={setSnapshot} onClose={() => setSettingsMode(null)} />
      <ConfirmDialog open={leaveOpen} title={t('cd.leaveTitle', locale)} message={t('cd.leaveMessage', locale)} cancelLabel={t('cd.continueEditing', locale)} confirmLabel={t('cd.leave', locale)} onCancel={() => setLeaveOpen(false)} onConfirm={() => router.push('/custom-dashboards')} />
      <ConfirmDialog open={publishOpen} title={t('cd.publishTitle', locale, { name: snapshot.name })} message={`${t('cd.publishMessage', locale)}${warningCount > 0 ? ` ${t('cd.publishWarning', locale, { count: warningCount })}` : ''}`} confirmLabel={t('cd.publish', locale)} loading={publishDashboard.isPending} onCancel={() => setPublishOpen(false)} onConfirm={publish} />
      <ConfirmDialog open={deleteComponent !== null} title={t('cd.deleteComponentTitle', locale)} itemName={deleteComponent?.title} confirmLabel={t('cd.delete', locale)} variant="destructive" onCancel={() => setDeleteComponent(null)} onConfirm={() => { if (deleteComponent) setSnapshot({ ...snapshot, components: snapshot.components.filter((item) => item.id !== deleteComponent.id) }); setDeleteComponent(null) }} />
    </div>
  )
}
