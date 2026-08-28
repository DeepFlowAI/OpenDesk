'use client'

import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  IconCopy,
  IconGripVertical,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { DashboardCopyDialog } from './dashboard-copy-dialog'
import { DashboardIcon } from './dashboard-icon'
import type { DashboardListItem, DashboardStatus } from '@/models/custom-dashboard'
import {
  useCopyCustomDashboard,
  useCustomDashboards,
  useDeleteCustomDashboard,
  useDisableCustomDashboard,
  useEnableCustomDashboard,
  useReorderCustomDashboards,
} from '@/service/use-custom-dashboards'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type ConfirmAction = { kind: 'delete' | 'disable'; dashboard: DashboardListItem } | null

function formatDate(value: string | null, locale: string) {
  return value ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

function statusVariant(status: DashboardStatus): 'default' | 'secondary' | 'outline' {
  if (status === 'published') return 'default'
  if (status === 'disabled') return 'outline'
  return 'secondary'
}

export function DashboardList() {
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const deferredKeyword = useDeferredValue(keyword)
  const [status, setStatus] = useState<'all' | DashboardStatus>('all')
  const [sorting, setSorting] = useState(false)
  const [orderedIds, setOrderedIds] = useState<number[]>([])
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [copyTarget, setCopyTarget] = useState<DashboardListItem | null>(null)
  const query = useCustomDashboards({
    page: 1,
    per_page: 100,
    keyword: deferredKeyword || undefined,
    status: status === 'all' ? undefined : status,
  })
  const copyDashboard = useCopyCustomDashboard()
  const disableDashboard = useDisableCustomDashboard()
  const enableDashboard = useEnableCustomDashboard()
  const deleteDashboard = useDeleteCustomDashboard()
  const reorderDashboards = useReorderCustomDashboards()
  const items = useMemo(() => query.data?.items ?? [], [query.data?.items])

  useEffect(() => {
    if (!sorting) setOrderedIds(items.map((item) => item.id))
  }, [items, sorting])

  const rowsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items])
  const rows = orderedIds.map((id) => rowsById.get(id)).filter(Boolean) as DashboardListItem[]
  const mutating = copyDashboard.isPending || disableDashboard.isPending || enableDashboard.isPending || deleteDashboard.isPending || reorderDashboards.isPending

  function moveRow(toIndex: number) {
    if (dragIndex === null || dragIndex === toIndex) return setDragIndex(null)
    const next = [...orderedIds]
    const [removed] = next.splice(dragIndex, 1)
    next.splice(toIndex, 0, removed)
    setOrderedIds(next)
    setDragIndex(null)
  }

  async function saveOrder() {
    try {
      await reorderDashboards.mutateAsync(orderedIds)
      setSorting(false)
      toast.success(t('cd.orderSaved', locale))
    } catch {
      toast.error(t('cd.actionFailed', locale))
    }
  }

  async function confirmLifecycle() {
    if (!confirmAction) return
    try {
      if (confirmAction.kind === 'delete') {
        await deleteDashboard.mutateAsync(confirmAction.dashboard.id)
        toast.success(t('cd.deleted', locale))
      } else {
        await disableDashboard.mutateAsync(confirmAction.dashboard.id)
        toast.success(t('cd.disabledSuccess', locale))
      }
      setConfirmAction(null)
    } catch {
      toast.error(t('cd.actionFailed', locale))
    }
  }

  async function enable(dashboard: DashboardListItem) {
    try {
      await enableDashboard.mutateAsync(dashboard.id)
      toast.success(t('cd.enabledSuccess', locale))
    } catch {
      toast.error(t('cd.actionFailed', locale))
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('cd.title', locale)}</h1>
        <div className="flex gap-2">
          {sorting ? (
            <>
              <Button variant="outline" onClick={() => setSorting(false)}>{t('cd.cancel', locale)}</Button>
              <Button onClick={() => void saveOrder()} disabled={mutating}>{t('cd.saveOrder', locale)}</Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => setSorting(true)} disabled={items.length < 2}>{t('cd.sort', locale)}</Button>
          )}
          <Button render={<Link href="/custom-dashboards/new" />}><IconPlus />{t('cd.new', locale)}</Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <label className="flex h-9 w-72 items-center gap-2 rounded-lg border border-border px-3 focus-within:ring-2 focus-within:ring-ring/40">
          <IconSearch className="text-muted-foreground" size={16} />
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={t('cd.search', locale)} className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)} className="h-9 rounded-lg border border-border bg-background px-3 text-sm">
          <option value="all">{t('cd.status.all', locale)}</option>
          <option value="draft">{t('cd.status.draft', locale)}</option>
          <option value="published">{t('cd.status.published', locale)}</option>
          <option value="disabled">{t('cd.status.disabled', locale)}</option>
        </select>
      </div>

      {query.isLoading ? (
        <div className="rounded-xl border border-border p-16 text-center text-sm text-muted-foreground">{t('cd.loading', locale)}</div>
      ) : rows.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-border py-20">
          <p className="text-sm text-muted-foreground">{t('cd.empty', locale)}</p>
          <Button render={<Link href="/custom-dashboards/new" />}><IconPlus />{t('cd.new', locale)}</Button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <div className="min-w-[980px]">
            <div className="flex h-11 items-center gap-4 bg-muted px-4 text-xs font-semibold text-muted-foreground">
              <div className="w-12">{t('cd.col.order', locale)}</div><div className="min-w-48 flex-1">{t('cd.name', locale)}</div><div className="w-36">{t('cd.slug', locale)}</div><div className="w-24">{t('cd.col.status', locale)}</div><div className="w-20 text-center">{t('cd.col.components', locale)}</div><div className="w-40">{t('cd.col.publishedAt', locale)}</div><div className="w-40">{t('cd.col.updatedAt', locale)}</div><div className="w-56 text-right">{t('cd.col.actions', locale)}</div>
            </div>
            {rows.map((dashboard, index) => (
              <div key={dashboard.id} onDragOver={(event) => sorting && event.preventDefault()} onDrop={() => sorting && moveRow(index)} className="flex min-h-16 items-center gap-4 border-t border-border px-4 text-sm">
                <div className="w-12">
                  {sorting ? <button type="button" draggable onDragStart={() => setDragIndex(index)} onDragEnd={() => setDragIndex(null)} className="cursor-grab text-muted-foreground" aria-label={t('cd.drag', locale)}><IconGripVertical size={18} /></button> : <span className="font-mono text-xs text-muted-foreground">{dashboard.sort_order + 1}</span>}
                </div>
                <div className="flex min-w-48 flex-1 items-center gap-3"><span className="rounded-lg bg-muted p-2"><DashboardIcon name={dashboard.icon} /></span><Link href={`/custom-dashboards/${dashboard.id}`} className="min-w-0 truncate font-medium hover:underline">{dashboard.name}</Link></div>
                <div className="w-36 truncate font-mono text-xs">{dashboard.slug}</div>
                <div className="w-24"><Badge variant={statusVariant(dashboard.status)}>{t(`cd.status.${dashboard.status}`, locale)}</Badge></div>
                <div className="w-20 text-center font-mono text-xs">{dashboard.component_count}</div>
                <div className="w-40 text-xs text-muted-foreground">{formatDate(dashboard.published_at, locale)}</div>
                <div className="w-40 text-xs text-muted-foreground">{formatDate(dashboard.updated_at, locale)}</div>
                <div className="flex w-56 justify-end gap-1">
                  <Button render={<Link href={`/custom-dashboards/${dashboard.id}`} />} variant="ghost" size="icon-sm" aria-label={t('cd.edit', locale)}><IconPencil /></Button>
                  <Button variant="ghost" size="icon-sm" onClick={() => setCopyTarget(dashboard)} aria-label={t('cd.copy', locale)}><IconCopy /></Button>
                  {dashboard.status === 'disabled' ? <Button variant="ghost" size="sm" onClick={() => void enable(dashboard)}>{t('cd.enable', locale)}</Button> : dashboard.status === 'published' ? <Button variant="ghost" size="sm" onClick={() => setConfirmAction({ kind: 'disable', dashboard })}>{t('cd.disable', locale)}</Button> : null}
                  <Button variant="ghost" size="icon-sm" onClick={() => setConfirmAction({ kind: 'delete', dashboard })} aria-label={t('cd.delete', locale)}><IconTrash className="text-destructive" /></Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <DashboardCopyDialog dashboard={copyTarget} loading={copyDashboard.isPending} onClose={() => setCopyTarget(null)} onCopy={async (slug) => {
        if (!copyTarget) return
        try {
          await copyDashboard.mutateAsync({ id: copyTarget.id, slug })
          setCopyTarget(null)
          toast.success(t('cd.copied', locale))
        } catch { toast.error(t('cd.actionFailed', locale)) }
      }} />
      <ConfirmDialog open={confirmAction !== null} title={confirmAction?.kind === 'delete' ? t('cd.deleteTitle', locale) : t('cd.disableTitle', locale)} message={confirmAction?.kind === 'delete' ? t('cd.deleteMessage', locale) : t('cd.disableMessage', locale)} itemName={confirmAction?.dashboard.name} itemDescription={confirmAction?.kind === 'delete' ? (confirmAction.dashboard.description || '—') : undefined} confirmLabel={confirmAction?.kind === 'delete' ? t('cd.delete', locale) : t('cd.disable', locale)} variant={confirmAction?.kind === 'delete' ? 'destructive' : 'default'} loading={mutating} onCancel={() => setConfirmAction(null)} onConfirm={confirmLifecycle} />
    </div>
  )
}
