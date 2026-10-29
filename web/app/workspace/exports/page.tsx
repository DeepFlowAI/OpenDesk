'use client'

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { IconCheck, IconDownload, IconLoader2, IconRefresh, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/tiptap-ui-primitive/tooltip'
import { useLocaleStore } from '@/context/locale-store'
import type { ExportTask } from '@/models/export-task'
import {
  cancelExportTask, downloadExportTask, exportErrorCode, exportKeys, markExportsViewed,
  useExportForeground, useExportIdentity, useExportTasks,
} from '@/service/use-export-tasks'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

function localTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function Explanation({ text }: { text: string }) {
  return <Tooltip>
    <TooltipTrigger asChild>
      <p tabIndex={0} className="mt-1 max-w-64 line-clamp-2 text-xs text-muted-foreground">{text}</p>
    </TooltipTrigger>
    <TooltipContent className="max-w-sm">{text}</TooltipContent>
  </Tooltip>
}

export default function ExportTasksPage() {
  const identity = useExportIdentity()
  return <PersonalExportTasks key={identity} />
}

function PersonalExportTasks() {
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [cancelTask, setCancelTask] = useState<ExportTask | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [downloads, setDownloads] = useState<Set<string>>(new Set())
  const [errors, setErrors] = useState<Record<string, string>>({})
  const query = useExportTasks(page, perPage)
  const visible = useExportForeground()
  const qc = useQueryClient()
  const marking = useRef(false)
  const cancelBusy = useRef(false)
  const downloadBusy = useRef(new Set<string>())
  const data = query.data
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const localized = (values: Record<string, string>) => values[locale] ?? values.zh ?? values.en ?? ''

  useEffect(() => {
    if (data && !query.isPlaceholderData && data.page !== page) setPage(data.page)
  }, [data, page, query.isPlaceholderData])

  useEffect(() => {
    if (!visible || !data || query.isPlaceholderData || query.isError || marking.current) return
    const ids = data.items.filter((item) => !item.viewed && ['completed', 'failed', 'expired'].includes(item.status)).map((item) => item.id)
    if (!ids.length) return
    marking.current = true
    void markExportsViewed(ids).then(() => {
      void qc.invalidateQueries({ queryKey: exportKeys, predicate: (item) => item.queryKey[2] === 'status' })
    }).catch(() => { /* Retry after the next successful page refresh. */ }).finally(() => { marking.current = false })
  }, [data, query.dataUpdatedAt, query.isPlaceholderData, query.isError, visible, qc])

  const refresh = () => qc.invalidateQueries({ queryKey: exportKeys })
  const cancel = async () => {
    if (!cancelTask || cancelBusy.current) return
    cancelBusy.current = true
    setCancelling(true)
    try {
      await cancelExportTask(cancelTask.id)
      toast.success(t('exports.cancelled', locale))
      setCancelTask(null)
    } catch (error) {
      const code = await exportErrorCode(error)
      toast.error(t(`exports.error.${code === 'download_failed' ? 'cancel_failed' : code}`, locale))
      if (code === 'already_completed' || code === 'not_found' || code === 'not_cancellable') setCancelTask(null)
    } finally {
      cancelBusy.current = false
      setCancelling(false)
      void refresh()
    }
  }

  const download = async (task: ExportTask) => {
    if (downloadBusy.current.has(task.id)) return
    downloadBusy.current.add(task.id)
    setDownloads(new Set(downloadBusy.current))
    try {
      const { url } = await downloadExportTask(task.id)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.referrerPolicy = 'no-referrer'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      setErrors((previous) => { const next = { ...previous }; delete next[task.id]; return next })
      toast.success(t('exports.downloadStarted', locale))
    } catch (error) {
      const code = await exportErrorCode(error)
      setErrors((previous) => ({ ...previous, [task.id]: code }))
      toast.error(t(`exports.error.${code}`, locale))
      void refresh()
    } finally {
      downloadBusy.current.delete(task.id)
      setDownloads(new Set(downloadBusy.current))
    }
  }

  if (query.error instanceof HTTPError && query.error.response.status === 403) {
    return <div className="p-6"><h1 className="text-xl font-semibold">403</h1><p className="mt-2 text-muted-foreground">{t('exports.error.forbidden', locale)}</p></div>
  }

  return <div className="flex min-w-0 flex-col gap-4 p-6">
    <div className="flex items-start justify-between gap-3">
      <div><h1 className="text-xl font-semibold">{t('exports.title', locale)}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('exports.description', locale)}</p></div>
      <Button variant="secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>
        {query.isFetching ? <IconLoader2 className="animate-spin" /> : <IconRefresh />}{t('exports.refresh', locale)}
      </Button>
    </div>
    {query.isError && <div role="alert" className="flex items-center gap-3 rounded-lg border border-destructive/30 p-4 text-sm text-destructive">
      {t(data ? 'exports.refreshFailed' : 'exports.loadFailed', locale)}
      <Button variant="ghost" disabled={query.isFetching} onClick={() => void query.refetch()}>{t('exports.refresh', locale)}</Button>
    </div>}
    {!data && !query.isError ? <div role="status" aria-label={t('exports.loading', locale)} className="space-y-3 rounded-lg border border-border p-4">
      <span className="sr-only">{t('exports.loading', locale)}</span>
      {[0, 1, 2, 3].map((row) => <div key={row} className="h-12 animate-pulse rounded bg-muted" />)}
    </div> : data && data.total === 0 ? <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-background py-20 text-muted-foreground">
      <IconDownload size={32} /><p className="text-sm">{t('exports.empty', locale)}</p>
    </div> : data && <>
      <div className="overflow-x-auto rounded-lg border border-border bg-background">
        <Table className="min-w-[1120px]">
          <TableHeader className="bg-muted"><TableRow>
            {['content', 'type', 'submitted', 'status', 'rows', 'file', 'expires', 'actions'].map((column) =>
              <TableHead key={column} className="px-4">{t(`exports.column.${column}`, locale)}</TableHead>)}
          </TableRow></TableHeader>
          <TableBody>{data.items.map((task) => {
            const pending = task.status === 'pending' || task.status === 'running'
            const reason = errors[task.id] ?? task.error_code
            const denied = ['access_changed', 'expired', 'file_unavailable', 'not_found'].includes(reason ?? '')
            return <TableRow key={task.id}>
              <TableCell className="min-w-48 px-4 py-4"><p className="font-medium">{localized(task.name)}</p>
                <p className="mt-1 max-w-64 text-xs text-muted-foreground">{localized(task.summary)}</p></TableCell>
              <TableCell className="px-4">{localized(task.business_type)}</TableCell>
              <TableCell className="px-4 whitespace-nowrap"><time dateTime={task.created_at} title={timezone}>{localTime(task.created_at)}</time></TableCell>
              <TableCell className="px-4"><span className={cn('inline-flex items-center gap-1.5 text-sm',
                task.status === 'completed' && 'text-success', task.status === 'failed' && 'text-destructive',
                ['cancelled', 'expired'].includes(task.status) && 'text-muted-foreground')}>
                {pending ? <IconLoader2 size={14} className="animate-spin" /> : task.status === 'completed' ? <IconCheck size={14} /> : null}
                {t(`exports.status.${task.status}`, locale)}</span>
                {reason && <Explanation text={t(`exports.error.${reason.startsWith('cell_limit_') ? 'cell_limit' : reason}`, locale, { field: task.error_field ?? '—' })} />}
                {task.scope_reduced && <Explanation text={t('exports.scopeReduced', locale)} />}
                {task.row_count === 0 && <Explanation text={t('exports.noData', locale)} />}
              </TableCell>
              <TableCell className="px-4 tabular-nums">{task.row_count?.toLocaleString() ?? '—'}</TableCell>
              <TableCell className="px-4 whitespace-nowrap">{task.file_name && task.file_size !== null
                ? `${task.file_name.split('.').pop()?.toUpperCase()} · ${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(task.file_size / 1024)} KB` : '—'}</TableCell>
              <TableCell className="px-4 whitespace-nowrap"><time dateTime={task.expires_at ?? undefined} title={timezone}>{localTime(task.expires_at)}</time></TableCell>
              <TableCell className="px-4">{pending ? <Button variant="ghost" disabled={cancelling && cancelTask?.id === task.id} onClick={() => setCancelTask(task)}>
                <IconX />{t('exports.cancel', locale)}</Button> : task.can_download && !denied ? <Button variant="ghost" disabled={downloads.has(task.id)} onClick={() => void download(task)}>
                {downloads.has(task.id) ? <IconLoader2 className="animate-spin" /> : <IconDownload />}
                {t(downloads.has(task.id) ? 'exports.preparing' : 'exports.download', locale)}</Button> : '—'}</TableCell>
            </TableRow>
          })}</TableBody>
        </Table>
      </div>
      <nav aria-label={t('exports.pagination', locale)} className="flex flex-wrap items-center justify-end gap-3 text-sm">
        <span className="text-muted-foreground">{t('exports.total', locale, { count: data.total })}</span>
        <Select value={String(perPage)} onValueChange={(value) => { setPerPage(Number(value)); setPage(1) }}>
          <SelectTrigger aria-label={t('exports.perPage', locale)}><SelectValue /></SelectTrigger>
          <SelectContent>{[20, 50, 100].map((size) => <SelectItem key={size} value={String(size)}>{t('exports.pageSize', locale, { count: size })}</SelectItem>)}</SelectContent>
        </Select>
        <Button variant="outline" disabled={page <= 1 || query.isPlaceholderData} onClick={() => setPage(page - 1)}>{t('exports.previous', locale)}</Button>
        <span>{data.page} / {data.pages}</span>
        <Button variant="outline" disabled={page >= data.pages || query.isPlaceholderData} onClick={() => setPage(page + 1)}>{t('exports.next', locale)}</Button>
      </nav>
    </>}
    <Dialog open={Boolean(cancelTask)} onOpenChange={(open) => { if (!open && !cancelling) setCancelTask(null) }}>
      <DialogContent showCloseButton={false}>
        <DialogTitle>{t('exports.cancelTitle', locale)}</DialogTitle>
        <DialogDescription>{t('exports.cancelDescription', locale)}</DialogDescription>
        <DialogFooter>
          <Button variant="outline" disabled={cancelling} onClick={() => setCancelTask(null)}>{t('exports.keepWaiting', locale)}</Button>
          <Button variant="destructive" disabled={cancelling} onClick={() => void cancel()}>
            {cancelling && <IconLoader2 className="animate-spin" />}{t(cancelling ? 'exports.cancelling' : 'exports.cancelExport', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
}
