'use client'

import Link from 'next/link'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import {
  IconArrowLeft,
  IconPlus,
  IconTrash,
  IconUpload,
} from '@tabler/icons-react'
import { HTTPError } from 'ky'
import { toast } from 'sonner'
import { AutoOutboundTaskForm } from '@/app/components/features/engagement/auto-outbound-task-form'
import { RecordsPanel } from '@/app/components/features/engagement/auto-outbound-records-panel'
import { outboundFieldTreeNodes } from '@/app/components/features/call-center/outbound-task-fields'
import { FieldValueDisplay } from '@/app/components/features/field-system'
import {
  AutoTargetStatusBadge,
  AutoTaskStatusBadge,
  DailyTrendBars,
  ExecutionModeBadge,
  MetricCard,
  SimpleBarChart,
  SimplePagination,
  TableSkeleton,
  formatAnswerRate,
  localizedAutoPauseReason,
} from '@/app/components/features/engagement/auto-outbound-task-ui'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import {
  readAutoOutboundErrorMessage,
  readLocalizedAutoOutboundError,
} from '@/lib/auto-outbound-api-error'
import {
  abandonRateLimitApiToFormPercent,
  importResultToastParams,
  isAbandonOverLimit,
  toFiniteNumber,
} from '@/lib/auto-outbound-numbers'
import { mapResultDistributionItems } from '@/lib/auto-outbound-stats'
import {
  autoOutboundTargetDetailFields,
  autoOutboundTargetListFields,
} from '@/lib/auto-outbound-target-fields'
import type {
  AutoOutboundTarget,
  AutoOutboundTargetImportResponse,
  AutoOutboundTargetStatus,
  AutoOutboundTask,
  AutoOutboundTaskStatus,
} from '@/models/auto-outbound-task'
import type { OutboundTaskField } from '@/models/outbound-task'
import {
  useAutoOutboundMonitor,
  useAutoOutboundRecords,
  useAutoOutboundTargets,
  useAutoOutboundTask,
  useAutoOutboundTaskStats,
  useCreateAutoOutboundTarget,
  useDeleteAutoOutboundTarget,
  useDeleteAutoOutboundTask,
  useImportAutoOutboundTargets,
  useMarkAutoOutboundTargetInvalid,
  useTransitionAutoOutboundTask,
  useUpdateAutoOutboundTask,
} from '@/service/use-auto-outbound-tasks'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'

type DetailTab = 'targets' | 'records' | 'stats' | 'monitor'
type ConfirmAction = 'pause' | 'archive' | 'deleteTask' | null

const TARGETS_PAGE_SIZE = 100
const RECORDS_PAGE_SIZE = 50
// Task statuses that allow appending targets (import / manual add).
const TARGET_APPENDABLE_STATUSES: AutoOutboundTaskStatus[] = ['draft', 'active', 'paused']

export default function AutoOutboundTaskDetailPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const taskId = Number(params.taskId)
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)

  const [editing, setEditing] = useState(false)
  const [activeTab, setActiveTab] = useState<DetailTab>('targets')
  const [targetStatus, setTargetStatus] = useState<'' | AutoOutboundTargetStatus>('')
  const [importOpen, setImportOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [addNumbers, setAddNumbers] = useState('')
  const [addFailures, setAddFailures] = useState<Array<{ phone: string; reason: string }>>([])
  const [selectedTarget, setSelectedTarget] = useState<AutoOutboundTarget | null>(null)
  const [deleteTargetCandidate, setDeleteTargetCandidate] = useState<AutoOutboundTarget | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)

  const page = Number(searchParams.get('page') ?? '1') || 1

  const {
    data: task,
    isLoading,
    isError: taskError,
    error: taskQueryError,
  } = useAutoOutboundTask(taskId)
  // Shared URL `page` applies to the active list tab; keep targets on page 1
  // when browsing other tabs (badge total + record→target lookup).
  const { data: targets, isLoading: targetsLoading } = useAutoOutboundTargets(taskId, {
    page: activeTab === 'targets' ? page : 1,
    page_size: TARGETS_PAGE_SIZE,
    status: targetStatus || undefined,
  })
  const { data: records, isLoading: recordsLoading } = useAutoOutboundRecords(
    taskId,
    { page: activeTab === 'records' ? page : 1, page_size: RECORDS_PAGE_SIZE },
    activeTab === 'records',
  )
  const { data: stats } = useAutoOutboundTaskStats(taskId, activeTab === 'stats')
  const monitorEnabled = activeTab === 'monitor'
  const { data: monitor } = useAutoOutboundMonitor(taskId, monitorEnabled)

  const createTarget = useCreateAutoOutboundTarget(taskId)
  const importTargets = useImportAutoOutboundTargets(taskId)
  const deleteTarget = useDeleteAutoOutboundTarget()
  const deleteTask = useDeleteAutoOutboundTask()
  const markInvalid = useMarkAutoOutboundTargetInvalid()
  const transition = useTransitionAutoOutboundTask()
  const updateTask = useUpdateAutoOutboundTask()

  useEffect(() => {
    const tab = searchParams.get('tab') as DetailTab | null
    if (tab && ['targets', 'records', 'stats', 'monitor'].includes(tab)) setActiveTab(tab)
  }, [searchParams])

  const canManage = useMemo(() => {
    if (!task || !user) return false
    if (hasPermission(user, 'engagement.auto_outbound_task.manage')) return true
    if (!hasPermission(user, 'engagement.auto_outbound_task.create')) return false
    return task.created_by_id != null && task.created_by_id === user.id
  }, [task, user])
  const taskAllowsTargetDelete = task
    ? TARGET_APPENDABLE_STATUSES.includes(task.status)
    : false

  const canViewCallRecord = hasPermission(user, 'call.record.view')
  const canManageSubscription = hasPermission(
    user,
    'engagement.auto_outbound_task.subscription.manage',
  )

  const backHref = useMemo(() => {
    const from = searchParams.get('from')
    return from
      ? `/workspace/engagement/auto-outbound-tasks?${from}`
      : '/workspace/engagement/auto-outbound-tasks'
  }, [searchParams])

  const replaceQuery = (patch: { tab?: DetailTab; page?: number }) => {
    const params = new URLSearchParams(searchParams.toString())
    if (patch.tab) {
      params.set('tab', patch.tab)
      setActiveTab(patch.tab)
    }
    if ('page' in patch) {
      if (patch.page && patch.page > 1) params.set('page', String(patch.page))
      else params.delete('page')
    }
    const qs = params.toString()
    router.replace(
      qs
        ? `/workspace/engagement/auto-outbound-tasks/${taskId}?${qs}`
        : `/workspace/engagement/auto-outbound-tasks/${taskId}`,
    )
  }

  const selectTab = (tab: DetailTab) => {
    replaceQuery({ tab, page: 1 })
  }

  const setPage = (next: number) => {
    replaceQuery({ page: next })
  }

  const runTransition = async (action: 'start' | 'pause' | 'resume' | 'archive') => {
    try {
      await transition.mutateAsync({ id: taskId, action })
      if (action === 'start') toast.success(t('ws.autoOutbound.toast.started', locale))
      else if (action === 'pause') toast.success(t('ws.autoOutbound.toast.paused', locale))
      else if (action === 'resume') toast.success(t('ws.autoOutbound.toast.resumed', locale))
      else toast.success(t('ws.autoOutbound.toast.archived', locale))
      setConfirmAction(null)
    } catch (err) {
      const fallback =
        action === 'start'
          ? t('ws.autoOutbound.toast.startFailed', locale)
          : t('ws.autoOutbound.toast.actionFailed', locale)
      toast.error(await readLocalizedAutoOutboundError(err, locale, fallback))
    }
  }

  const pendingCount = useMemo(() => {
    if (!targets) return 0
    return targets.items.filter((item) => item.status === 'pending' || item.status === 'redial_pending').length
  }, [targets])
  const targetDetailFields = useMemo(
    () => autoOutboundTargetDetailFields(task?.fields ?? []),
    [task?.fields],
  )

  useEffect(() => {
    if (!selectedTarget || !targets) return
    const latest = targets.items.find((item) => item.id === selectedTarget.id)
    if (!latest) {
      setSelectedTarget(null)
    } else if (latest !== selectedTarget) {
      setSelectedTarget(latest)
    }
  }, [selectedTarget, targets])

  if (editing && task) {
    return (
      <div className="h-full overflow-hidden">
          <AutoOutboundTaskForm
            locale={locale}
            mode="edit"
            header={(
              <div className="flex items-center gap-3 px-6 py-4">
                <button type="button" onClick={() => setEditing(false)} className="rounded-md p-2 hover:bg-muted">
                  <IconArrowLeft size={18} />
                </button>
                <div>
                  <h1 className="text-xl font-semibold">{t('ws.autoOutbound.edit.title', locale)}</h1>
                  <p className="mt-1 text-sm text-muted-foreground">{task.name}</p>
                </div>
              </div>
            )}
            initial={task}
            currentUserId={user?.id}
            lockExecution={task.status !== 'draft'}
            submitting={updateTask.isPending || transition.isPending}
            onCancel={() => setEditing(false)}
            onSaveDraft={async (values) => {
              try {
                await updateTask.mutateAsync({ id: taskId, data: values })
                toast.success(t('ws.autoOutbound.toast.updated', locale))
                setEditing(false)
              } catch (err) {
                toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.saveFailed', locale)))
              }
            }}
            onStart={async (values) => {
              try {
                await updateTask.mutateAsync({ id: taskId, data: values })
                if ((task.stats.total_targets ?? 0) <= 0) {
                  toast.error(t('ws.autoOutbound.validation.emptyTargets', locale))
                  setEditing(false)
                  return
                }
                await transition.mutateAsync({ id: taskId, action: 'start' })
                toast.success(t('ws.autoOutbound.toast.started', locale))
                setEditing(false)
              } catch (err) {
                toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.startFailed', locale)))
              }
            }}
          />
      </div>
    )
  }

  const taskErrorStatus = taskQueryError instanceof HTTPError ? taskQueryError.response.status : 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href={backHref} className="rounded-md p-2 hover:bg-muted" title={t('ws.autoOutbound.detail.back', locale)}>
            <IconArrowLeft size={18} />
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-foreground">{task?.name ?? t('ws.autoOutbound.list.title', locale)}</h1>
              {task && <ExecutionModeBadge mode={task.execution_mode} locale={locale} />}
              {task && (
                <AutoTaskStatusBadge
                  status={task.status}
                  outOfWindow={task.out_of_window}
                  autoPauseReason={task.auto_pause_reason}
                  locale={locale}
                />
              )}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{task?.template_name ?? '—'}</p>
          </div>
        </div>
        {task && canManage && (
          <div className="flex flex-wrap gap-2">
            {canManageSubscription && (
              <Link
                href={`/workspace/engagement/auto-outbound-tasks/${taskId}/event-subscription`}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                {t('ws.autoOutbound.subscription.title', locale)}
              </Link>
            )}
            {(task.status === 'draft' || task.status === 'paused' || task.status === 'active') && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                {t('ws.autoOutbound.action.edit', locale)}
              </button>
            )}
            {task.status === 'draft' && (
              <button
                type="button"
                onClick={() => setConfirmAction('deleteTask')}
                className="rounded-md border border-border px-3 py-2 text-sm text-destructive"
              >
                {t('ws.autoOutbound.action.delete', locale)}
              </button>
            )}
            {task.status === 'draft' && (
              <button
                type="button"
                onClick={() => {
                  if ((task.stats.total_targets ?? 0) <= 0) {
                    toast.error(t('ws.autoOutbound.validation.emptyTargets', locale))
                    return
                  }
                  void runTransition('start')
                }}
                className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
              >
                {t('ws.autoOutbound.action.start', locale)}
              </button>
            )}
            {task.status === 'active' && (
              <button
                type="button"
                onClick={() => setConfirmAction('pause')}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                {t('ws.autoOutbound.action.pause', locale)}
              </button>
            )}
            {task.status === 'paused' && (
              <button
                type="button"
                onClick={() => void runTransition('resume')}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                {t('ws.autoOutbound.action.resume', locale)}
              </button>
            )}
            {(task.status === 'paused' || task.status === 'completed' || task.status === 'active') && (
              <button
                type="button"
                onClick={() => setConfirmAction('archive')}
                className="rounded-md border border-border px-3 py-2 text-sm"
              >
                {t('ws.autoOutbound.action.archive', locale)}
              </button>
            )}
          </div>
        )}
      </header>

      <main className="min-h-0 flex-1 overflow-auto p-6">
        {isLoading ? (
          <TableSkeleton rows={4} cols={4} />
        ) : taskError || !task ? (
          <EmptyState
            title={
              taskErrorStatus === 403
                ? t('ws.autoOutbound.forbidden', locale)
                : t('ws.autoOutbound.detail.loadFailed', locale)
            }
            action={(
              <Link href={backHref} className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">
                {t('ws.autoOutbound.detail.back', locale)}
              </Link>
            )}
          />
        ) : (
          <div className="space-y-6">
            {task.status === 'paused' && task.auto_pause_reason ? (
              <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
                {t('ws.autoOutbound.detail.autoPauseReason', locale, {
                  reason: localizedAutoPauseReason(task.auto_pause_reason, locale),
                })}
              </div>
            ) : null}

            <section className="flex items-center justify-between rounded-lg border border-border bg-background px-4 py-3 text-sm">
              <span className="text-muted-foreground">
                {t('ws.autoOutbound.detail.autoResumeOnAppend', locale)}
              </span>
              <span className="font-medium">
                {t(
                  task.auto_resume_on_target_append
                    ? 'ws.autoOutbound.value.enabled'
                    : 'ws.autoOutbound.value.disabled',
                  locale,
                )}
              </span>
            </section>

            <OverviewMetrics task={task} locale={locale} />

            <section>
              <div className="flex items-center justify-between border-b border-border px-1">
                <div role="tablist" className="flex gap-6">
                  {(
                    [
                      ['targets', 'ws.autoOutbound.tab.targets'],
                      ['records', 'ws.autoOutbound.tab.records'],
                      ['stats', 'ws.autoOutbound.tab.stats'],
                      ['monitor', 'ws.autoOutbound.tab.monitor'],
                    ] as Array<[DetailTab, string]>
                  ).map(([tab, labelKey]) => (
                    <button
                      key={tab}
                      type="button"
                      role="tab"
                      aria-selected={activeTab === tab}
                      onClick={() => selectTab(tab)}
                      className={`border-b-2 px-1 pb-3 text-sm font-medium transition-colors ${
                        activeTab === tab
                          ? 'border-foreground text-foreground'
                          : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {t(labelKey, locale)}
                      {tab === 'targets' && (
                        <span className="ml-2 text-xs text-muted-foreground">{targets?.total ?? 0}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pt-4">
                {activeTab === 'targets' && (
                  <TargetsPanel
                    locale={locale}
                    task={task}
                    canManage={canManage}
                    targets={targets?.items ?? []}
                    total={targets?.total ?? 0}
                    page={page}
                    pageSize={TARGETS_PAGE_SIZE}
                    loading={targetsLoading}
                    status={targetStatus}
                    onStatusChange={(value) => {
                      setTargetStatus(value)
                      setPage(1)
                    }}
                    onPageChange={setPage}
                    onImport={() => {
                      setImportFile(null)
                      importTargets.reset()
                      setImportOpen(true)
                    }}
                    onAdd={() => {
                      setAddNumbers('')
                      setAddFailures([])
                      setAddOpen(true)
                    }}
                    onView={setSelectedTarget}
                    onMarkInvalid={async (id) => {
                      try {
                        await markInvalid.mutateAsync(id)
                        toast.success(t('ws.autoOutbound.toast.markedInvalid', locale))
                      } catch (err) {
                        toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.actionFailed', locale)))
                      }
                    }}
                  />
                )}

                {activeTab === 'records' && (
                  <>
                    <RecordsPanel
                      locale={locale}
                      loading={recordsLoading}
                      items={records?.items ?? []}
                      canViewCallRecord={canViewCallRecord}
                      onOpenTarget={(targetId) => {
                        const found = targets?.items.find((item) => item.id === targetId)
                        if (found) {
                          setSelectedTarget(found)
                          return
                        }
                        toast.info(t('ws.autoOutbound.toast.targetNotOnPage', locale))
                      }}
                    />
                    <SimplePagination
                      page={page}
                      pageSize={RECORDS_PAGE_SIZE}
                      total={records?.total ?? 0}
                      locale={locale}
                      onPageChange={setPage}
                    />
                  </>
                )}

                {activeTab === 'stats' && (
                  <StatsPanel locale={locale} task={task} stats={stats} />
                )}

                {activeTab === 'monitor' && (
                  <MonitorPanel
                    locale={locale}
                    running={task.status === 'active'}
                    agentMode={task.execution_mode === 'agent'}
                    monitor={monitor}
                    abandonLimit={task.abandon_rate_limit}
                  />
                )}
              </div>
            </section>
          </div>
        )}
      </main>

      <ImportTargetsDialog
        open={importOpen}
        locale={locale}
        fields={task?.fields ?? []}
        file={importFile}
        result={importTargets.data}
        submitting={importTargets.isPending}
        onFileChange={setImportFile}
        onClose={() => setImportOpen(false)}
        onSubmit={async () => {
          if (!importFile) return
          try {
            const result = await importTargets.mutateAsync(importFile)
            toast.success(
              result.task_auto_resumed
                ? t('ws.autoOutbound.toast.addedAndResumed', locale)
                : t('ws.autoOutbound.toast.importResult', locale, importResultToastParams(result)),
            )
            if (result.errors.length === 0) {
              setImportOpen(false)
              setImportFile(null)
              selectTab('targets')
            }
          } catch (err) {
            toast.error(await readLocalizedAutoOutboundError(err, locale, t('ws.autoOutbound.toast.importFailed', locale)))
          }
        }}
      />

      <Dialog open={addOpen} onOpenChange={(open) => { if (!open && !createTarget.isPending) setAddOpen(false) }}>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.add.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.add.desc', locale)}</DialogDescription>
          </DialogHeader>
          <textarea
            value={addNumbers}
            onChange={(e) => setAddNumbers(e.target.value)}
            className="min-h-40 rounded-md border border-border bg-background px-3 py-2 text-sm outline-none"
          />
          {addFailures.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <p className="font-medium">{t('ws.autoOutbound.add.failures', locale)}</p>
              <ul className="mt-1 list-disc pl-4 text-xs">
                {addFailures.map((item) => (
                  <li key={item.phone}>
                    {t('ws.autoOutbound.add.failureItem', locale, {
                      phone: item.phone,
                      reason: item.reason,
                    })}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <DialogFooter className="pb-0">
            <button type="button" onClick={() => setAddOpen(false)} className="h-10 rounded-md border border-border px-3 text-sm">
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              disabled={createTarget.isPending}
              onClick={async () => {
                const phones = parsePhoneNumbers(addNumbers)
                if (!phones.length) return
                const blockedReason = task?.status === 'completed'
                  ? t('ws.autoOutbound.validation.taskCompleted', locale)
                  : task?.status === 'archived'
                    ? t('ws.autoOutbound.validation.taskArchived', locale)
                    : null
                if (blockedReason) {
                  setAddFailures(phones.map((phone) => ({ phone, reason: blockedReason })))
                  toast.error(blockedReason)
                  return
                }
                let created = 0
                let taskAutoResumed = false
                const failures: Array<{ phone: string; reason: string }> = []
                const fallback = t('ws.autoOutbound.toast.addFailed', locale)
                for (const phone of phones) {
                  try {
                    const result = await createTarget.mutateAsync({ phone_number: phone, field_values: {} })
                    created += 1
                    taskAutoResumed ||= result.task_auto_resumed
                  } catch (err) {
                    failures.push({
                      phone,
                      reason: await readLocalizedAutoOutboundError(err, locale, fallback),
                    })
                  }
                }
                setAddFailures(failures)
                if (taskAutoResumed) {
                  if (failures.length === 0) setAddOpen(false)
                  toast.success(t('ws.autoOutbound.toast.addedAndResumed', locale))
                } else if (failures.length === 0) {
                  setAddOpen(false)
                  toast.success(t('ws.autoOutbound.toast.added', locale, { count: created }))
                } else if (created > 0) {
                  toast.success(t('ws.autoOutbound.toast.addedPartial', locale, {
                    created,
                    failed: failures.length,
                  }))
                } else {
                  const uniqueReasons = [...new Set(failures.map((item) => item.reason))]
                  toast.error(uniqueReasons.length === 1 ? uniqueReasons[0] : fallback)
                }
              }}
              className="h-10 rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
            >
              {t('ws.autoOutbound.add.submit', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteTargetCandidate != null}
        onOpenChange={(open) => {
          if (!open && !deleteTarget.isPending) setDeleteTargetCandidate(null)
        }}
      >
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.deleteTarget.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.deleteTarget.body', locale)}</DialogDescription>
          </DialogHeader>
          {deleteTargetCandidate && (
            <div className="space-y-3">
              <div className="space-y-2 rounded-md border border-border p-3 text-sm">
                <div className="flex justify-between gap-4">
                  <span className="text-muted-foreground">
                    {t('ws.autoOutbound.deleteTarget.phone', locale)}
                  </span>
                  <span className="font-medium">{deleteTargetCandidate.phone_number}</span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-muted-foreground">
                    {t('ws.autoOutbound.deleteTarget.user', locale)}
                  </span>
                  <span className="font-medium">
                    {deleteTargetCandidate.user_name
                      || t('ws.autoOutbound.deleteTarget.notMatched', locale)}
                  </span>
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('ws.autoOutbound.deleteTarget.impact', locale)}
              </p>
            </div>
          )}
          <DialogFooter className="pb-0">
            <button
              type="button"
              autoFocus
              disabled={deleteTarget.isPending}
              onClick={() => setDeleteTargetCandidate(null)}
              className="h-10 rounded-md border border-border px-3 text-sm disabled:opacity-50"
            >
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              disabled={deleteTarget.isPending}
              onClick={async () => {
                if (!deleteTargetCandidate) return
                try {
                  await deleteTarget.mutateAsync(deleteTargetCandidate.id)
                  const shouldGoToPreviousPage = page > 1 && targets?.items.length === 1
                  setDeleteTargetCandidate(null)
                  setSelectedTarget(null)
                  if (shouldGoToPreviousPage) setPage(page - 1)
                  toast.success(t('ws.autoOutbound.toast.deleted', locale))
                } catch (err) {
                  const status = err instanceof HTTPError ? err.response.status : 0
                  toast.error(await readLocalizedAutoOutboundError(
                    err,
                    locale,
                    t('ws.autoOutbound.deleteTarget.error.failed', locale),
                  ))
                  if (status === 409) {
                    setSelectedTarget(deleteTargetCandidate)
                    setDeleteTargetCandidate(null)
                  } else if (status === 403 || status === 404) {
                    setSelectedTarget(null)
                    setDeleteTargetCandidate(null)
                  }
                }
              }}
              className="h-10 rounded-md bg-destructive px-3 text-sm text-white disabled:opacity-50"
            >
              {t(
                deleteTarget.isPending
                  ? 'ws.autoOutbound.deleteTarget.submitting'
                  : 'ws.autoOutbound.deleteTarget.confirm',
                locale,
              )}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmAction === 'deleteTask'} onOpenChange={(open) => { if (!open) setConfirmAction(null) }}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.deleteTask.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.deleteTask.body', locale)}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="pb-0">
            <button type="button" onClick={() => setConfirmAction(null)} className="h-10 rounded-md border border-border px-3 text-sm">
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              disabled={deleteTask.isPending}
              onClick={async () => {
                try {
                  await deleteTask.mutateAsync(taskId)
                  toast.success(t('ws.autoOutbound.toast.taskDeleted', locale))
                  router.push(backHref)
                } catch (err) {
                  toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.actionFailed', locale)))
                }
              }}
              className="h-10 rounded-md bg-destructive px-3 text-sm text-white disabled:opacity-50"
            >
              {t('ws.autoOutbound.deleteTask.confirm', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmAction === 'pause'} onOpenChange={(open) => { if (!open) setConfirmAction(null) }}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.pause.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.pause.body', locale)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-md border border-border p-3 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">{t('ws.autoOutbound.pause.taskName', locale)}</span>
              <span className="font-medium">{task?.name}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">{t('ws.autoOutbound.pause.pendingCount', locale)}</span>
              <span className="font-medium">{pendingCount}</span>
            </div>
          </div>
          <DialogFooter className="pb-0">
            <button type="button" onClick={() => setConfirmAction(null)} className="h-10 rounded-md border border-border px-3 text-sm">
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              onClick={() => void runTransition('pause')}
              className="h-10 rounded-md bg-primary px-3 text-sm text-primary-foreground"
            >
              {t('ws.autoOutbound.pause.confirm', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmAction === 'archive'} onOpenChange={(open) => { if (!open) setConfirmAction(null) }}>
        <DialogContent className="sm:max-w-[460px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.archive.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.archive.body', locale)}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-md border border-border p-3 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">{t('ws.autoOutbound.pause.taskName', locale)}</span>
              <span className="font-medium">{task?.name}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">{t('ws.autoOutbound.archive.targetCount', locale)}</span>
              <span className="font-medium">{task?.stats.total_targets ?? 0}</span>
            </div>
          </div>
          <DialogFooter className="pb-0">
            <button type="button" onClick={() => setConfirmAction(null)} className="h-10 rounded-md border border-border px-3 text-sm">
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              onClick={() => void runTransition('archive')}
              className="h-10 rounded-md bg-primary px-3 text-sm text-primary-foreground"
            >
              {t('ws.autoOutbound.archive.confirm', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={selectedTarget != null} onOpenChange={(open) => { if (!open) setSelectedTarget(null) }}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-[720px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.targetDrawer.title', locale)}</DialogTitle>
            <DialogDescription>{selectedTarget?.phone_number}</DialogDescription>
          </DialogHeader>
          {selectedTarget && (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.user', locale)}</span>
                <span>{selectedTarget.user_name || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.status', locale)}</span>
                <AutoTargetStatusBadge status={selectedTarget.status} locale={locale} />
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.calls', locale)}</span>
                <span>{yesNo(selectedTarget.call_count, locale)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.answered', locale)}</span>
                <span>{yesNo(selectedTarget.answered_count, locale)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.lastResult', locale)}</span>
                <span>{selectedTarget.last_call_result || '—'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('ws.autoOutbound.targets.col.retries', locale)}</span>
                <span>{selectedTarget.remaining_retries}</span>
              </div>
              {targetDetailFields.length > 0 && (
                <div className="space-y-3 border-t border-border pt-4">
                  <h3 className="font-medium">{t('ws.autoOutbound.targetDrawer.templateFields', locale)}</h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {targetDetailFields.map((field) => (
                      <div key={field.key} className="min-w-0 rounded-md border border-border p-3">
                        <div className="mb-1 text-xs font-medium text-muted-foreground">{field.name}</div>
                        <FieldValueDisplay
                          fieldType={field.field_type}
                          value={selectedTarget.field_values?.[field.key]}
                          typeConfig={field.type_config}
                          treeNodes={outboundFieldTreeNodes(field)}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          <DialogFooter className="pb-0">
            {canManage
              && taskAllowsTargetDelete
              && selectedTarget?.can_delete && (
              <button
                type="button"
                onClick={() => {
                  setDeleteTargetCandidate(selectedTarget)
                  setSelectedTarget(null)
                }}
                className="inline-flex h-10 items-center gap-2 rounded-md border border-destructive px-3 text-sm text-destructive"
              >
                <IconTrash size={16} />
                {t('ws.autoOutbound.deleteTarget.title', locale)}
              </button>
            )}
            {canManage
              && taskAllowsTargetDelete
              && selectedTarget
              && !selectedTarget.can_delete && (
              <p className="mr-auto text-sm text-muted-foreground">
                {t('ws.autoOutbound.deleteTarget.unavailable', locale)}
              </p>
            )}
            {canManage && selectedTarget && selectedTarget.status !== 'invalid' && (
              <button
                type="button"
                onClick={async () => {
                  try {
                    await markInvalid.mutateAsync(selectedTarget.id)
                    toast.success(t('ws.autoOutbound.toast.markedInvalid', locale))
                    setSelectedTarget(null)
                  } catch (err) {
                    toast.error(await readAutoOutboundErrorMessage(err, t('ws.autoOutbound.toast.actionFailed', locale)))
                  }
                }}
                className="h-10 rounded-md border border-border px-3 text-sm"
              >
                {t('ws.autoOutbound.action.markInvalid', locale)}
              </button>
            )}
            <button type="button" onClick={() => setSelectedTarget(null)} className="h-10 rounded-md bg-primary px-3 text-sm text-primary-foreground">
              {t('ws.autoOutbound.action.close', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function OverviewMetrics({
  task,
  locale,
}: {
  task: AutoOutboundTask
  locale: ReturnType<typeof useLocaleStore.getState>['locale']
}) {
  const showAbandon = task.execution_mode === 'agent'
    && (task.pacing_mode === 'ratio' || task.pacing_mode === 'predictive')
  const abandonDanger =
    showAbandon
    && task.pacing_mode === 'predictive'
    && isAbandonOverLimit(task.stats.abandon_rate, task.abandon_rate_limit)

  return (
    <section className="grid gap-4 md:grid-cols-4 xl:grid-cols-8">
      <MetricCard label={t('ws.autoOutbound.detail.metric.total', locale)} value={task.stats.total_targets} />
      <MetricCard label={t('ws.autoOutbound.detail.metric.finished', locale)} value={task.stats.finished_targets} />
      <MetricCard label={t('ws.autoOutbound.detail.metric.calls', locale)} value={task.stats.call_count} />
      <MetricCard label={t('ws.autoOutbound.detail.metric.answered', locale)} value={task.stats.answered_count} />
      <MetricCard
        label={t('ws.autoOutbound.detail.metric.answerRate', locale)}
        value={formatAnswerRate(task.stats.answer_rate)}
      />
      <MetricCard
        label={t('ws.autoOutbound.detail.metric.concurrency', locale)}
        value={task.stats.current_concurrency ?? '—'}
      />
      <MetricCard
        label={
          task.execution_mode === 'agent'
            ? t('ws.autoOutbound.detail.metric.dispatched', locale)
            : t('ws.autoOutbound.detail.metric.transfers', locale)
        }
        value={task.stats.transfer_count ?? '—'}
      />
      {showAbandon ? (
        <MetricCard
          label={t('ws.autoOutbound.detail.metric.abandonRate', locale)}
          value={formatAnswerRate(task.stats.abandon_rate)}
          danger={abandonDanger}
        />
      ) : (
        <MetricCard label={t('ws.autoOutbound.detail.metric.abandonRate', locale)} value="—" />
      )}
    </section>
  )
}

function TargetsPanel({
  locale,
  task,
  canManage,
  targets,
  total,
  page,
  pageSize,
  loading,
  status,
  onStatusChange,
  onPageChange,
  onImport,
  onAdd,
  onView,
  onMarkInvalid,
}: {
  locale: ReturnType<typeof useLocaleStore.getState>['locale']
  task: AutoOutboundTask
  canManage: boolean
  targets: AutoOutboundTarget[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  status: '' | AutoOutboundTargetStatus
  onStatusChange: (value: '' | AutoOutboundTargetStatus) => void
  onPageChange: (page: number) => void
  onImport: () => void
  onAdd: () => void
  onView: (target: AutoOutboundTarget) => void
  onMarkInvalid: (id: number) => void
}) {
  const listFields = autoOutboundTargetListFields(task.fields)

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border border-border p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">{t('ws.autoOutbound.targets.title', locale)}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t('ws.autoOutbound.targets.subtitle', locale)}</p>
        </div>
        {canManage && TARGET_APPENDABLE_STATUSES.includes(task.status) && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onAdd} className="inline-flex h-10 items-center gap-2 rounded-md border border-border px-3 text-sm">
              <IconPlus size={16} />
              {t('ws.autoOutbound.action.add', locale)}
            </button>
            <button type="button" onClick={onImport} className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-3 text-sm text-primary-foreground">
              <IconUpload size={16} />
              {t('ws.autoOutbound.action.import', locale)}
            </button>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value as '' | AutoOutboundTargetStatus)}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="">{t('ws.autoOutbound.targets.statusAll', locale)}</option>
          {(['pending', 'calling', 'redial_pending', 'completed', 'invalid'] as AutoOutboundTargetStatus[]).map((value) => (
            <option key={value} value={value}>{t(`ws.autoOutbound.targetStatus.${value}`, locale)}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <TableSkeleton cols={7} />
      ) : targets.length === 0 ? (
        <EmptyState
          title={t(
            status === 'pending' ? 'ws.autoOutbound.targets.emptyPending' : 'ws.autoOutbound.targets.empty',
            locale,
          )}
          action={
            canManage && TARGET_APPENDABLE_STATUSES.includes(task.status) ? (
              <button type="button" onClick={onImport} className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground">
                {t('ws.autoOutbound.action.import', locale)}
              </button>
            ) : null
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-max min-w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="min-w-32 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.phone', locale)}</th>
                  <th className="min-w-32 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.user', locale)}</th>
                  <th className="min-w-24 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.status', locale)}</th>
                  <th className="min-w-20 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.calls', locale)}</th>
                  <th className="min-w-20 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.answered', locale)}</th>
                  <th className="min-w-32 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.lastResult', locale)}</th>
                  <th className="min-w-28 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.retries', locale)}</th>
                  {listFields.map((field) => (
                    <th key={field.key} className="min-w-36 whitespace-nowrap px-4 py-3 font-medium">{field.name}</th>
                  ))}
                  <th className="min-w-36 whitespace-nowrap px-4 py-3 font-medium">{t('ws.autoOutbound.targets.col.actions', locale)}</th>
                </tr>
              </thead>
              <tbody>
                {targets.map((target) => (
                  <tr key={target.id} className="border-t border-border">
                    <td className="whitespace-nowrap px-4 py-3 font-medium">
                      <button
                        type="button"
                        className="text-primary underline-offset-2 hover:underline"
                        onClick={() => onView(target)}
                      >
                        {target.phone_number}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{target.user_name || '—'}</td>
                    <td className="px-4 py-3">
                      <AutoTargetStatusBadge status={target.status} locale={locale} />
                    </td>
                    <td className="px-4 py-3">{yesNo(target.call_count, locale)}</td>
                    <td className="px-4 py-3">{yesNo(target.answered_count, locale)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{target.last_call_result || '—'}</td>
                    <td className="px-4 py-3">{target.remaining_retries}</td>
                    {listFields.map((field) => (
                      <td key={field.key} className="max-w-64 px-4 py-3 text-muted-foreground">
                        <FieldValueDisplay
                          fieldType={field.field_type}
                          value={target.field_values?.[field.key]}
                          typeConfig={field.type_config}
                          treeNodes={outboundFieldTreeNodes(field)}
                        />
                      </td>
                    ))}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {canManage && target.status !== 'invalid' && (
                          <button
                            type="button"
                            className="text-sm text-muted-foreground hover:text-foreground"
                            onClick={() => onMarkInvalid(target.id)}
                          >
                            {t('ws.autoOutbound.action.markInvalid', locale)}
                          </button>
                        )}
                        {(!canManage || target.status === 'invalid') && <span className="text-muted-foreground">—</span>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <SimplePagination
            page={page}
            pageSize={pageSize}
            total={total}
            locale={locale}
            onPageChange={onPageChange}
          />
        </>
      )}
    </div>
  )
}

function StatsPanel({
  locale,
  task,
  stats,
}: {
  locale: ReturnType<typeof useLocaleStore.getState>['locale']
  task: AutoOutboundTask
  stats?: import('@/models/auto-outbound-task').AutoOutboundTaskStatsResponse
}) {
  const showAbandon = task.execution_mode === 'agent'
    && (task.pacing_mode === 'ratio' || task.pacing_mode === 'predictive')
  const abandonStats = stats?.abandon_stats
  const abandonLimitPercent = toFiniteNumber(task.abandon_rate_limit) != null
    ? abandonRateLimitApiToFormPercent(task.abandon_rate_limit, 0)
    : null

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-lg border border-border p-4">
        <h3 className="mb-4 text-sm font-semibold">{t('ws.autoOutbound.stats.daily', locale)}</h3>
        <DailyTrendBars items={stats?.daily_trend ?? []} emptyLabel={t('ws.autoOutbound.stats.empty', locale)} />
      </section>
      <section className="rounded-lg border border-border p-4">
        <h3 className="mb-4 text-sm font-semibold">{t('ws.autoOutbound.stats.terminal', locale)}</h3>
        <SimpleBarChart
          emptyLabel={t('ws.autoOutbound.stats.empty', locale)}
          items={(stats?.terminal_state_distribution ?? []).map((item) => ({
            label: t(`ws.autoOutbound.terminal.${item.terminal_state}`, locale),
            value: item.count,
          }))}
        />
      </section>
      <section className="rounded-lg border border-border p-4">
        <h3 className="mb-4 text-sm font-semibold">{t('ws.autoOutbound.stats.result', locale)}</h3>
        <SimpleBarChart
          emptyLabel={t('ws.autoOutbound.stats.empty', locale)}
          items={mapResultDistributionItems(task.execution_mode, stats?.result_distribution, locale).map(
            (item) => ({ label: item.label, value: item.count }),
          )}
        />
      </section>
      {showAbandon && (
        <section className="rounded-lg border border-border p-4">
          <h3 className="mb-4 text-sm font-semibold">{t('ws.autoOutbound.stats.abandon', locale)}</h3>
          <SimpleBarChart
            emptyLabel={t('ws.autoOutbound.stats.empty', locale)}
            items={[
              { label: t('ws.autoOutbound.terminal.answered', locale), value: abandonStats?.answered ?? 0 },
              {
                label: t('ws.autoOutbound.stats.abandonedItem', locale),
                value: abandonStats?.abandoned ?? 0,
                accent: true,
              },
            ]}
          />
          {task.pacing_mode === 'predictive' && abandonLimitPercent != null && (
            <p className="mt-3 text-xs text-muted-foreground">
              {t('ws.autoOutbound.field.abandonRateLimit', locale)}: {abandonLimitPercent}%
            </p>
          )}
        </section>
      )}
    </div>
  )
}

function formatCapacityValue(value: number | null | undefined): string {
  return value == null ? '—' : String(value)
}

function yesNo(count: number, locale: ReturnType<typeof useLocaleStore.getState>['locale']): string {
  return t(count > 0 ? 'ws.autoOutbound.targets.yes' : 'ws.autoOutbound.targets.no', locale)
}

function MonitorPanel({
  locale,
  running,
  agentMode,
  monitor,
  abandonLimit,
}: {
  locale: ReturnType<typeof useLocaleStore.getState>['locale']
  running: boolean
  agentMode: boolean
  monitor?: import('@/models/auto-outbound-task').AutoOutboundMonitorResponse
  abandonLimit: number | string | null
}) {
  const abandonDanger = isAbandonOverLimit(monitor?.abandon_rate, abandonLimit)
  const capacity = monitor?.dial_capacity
  const sources = capacity?.sources

  return (
    <div className="space-y-4">
      {!running && <EmptyState title={t('ws.autoOutbound.monitor.notRunning', locale)} />}
      {running && agentMode && monitor?.no_ready_agents && (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          {t('ws.autoOutbound.monitor.lowAgentsHint', locale)}
        </div>
      )}
      {running && agentMode && (
        <div className="grid gap-4 md:grid-cols-5">
          <MetricCard label={t('ws.autoOutbound.monitor.inFlight', locale)} value={monitor?.in_progress_calls ?? 0} />
          <MetricCard label={t('ws.autoOutbound.monitor.readyAgents', locale)} value={monitor?.ready_agents ?? 0} />
          <MetricCard label={t('ws.autoOutbound.monitor.inCallAgents', locale)} value={monitor?.in_call_agents ?? 0} />
          <MetricCard label={t('ws.autoOutbound.monitor.queued', locale)} value={monitor?.queued_count ?? 0} />
          <MetricCard
            label={t('ws.autoOutbound.monitor.abandonRate', locale)}
            value={formatAnswerRate(monitor?.abandon_rate ?? null)}
            danger={abandonDanger}
          />
        </div>
      )}
      {capacity && (
        <div className="space-y-3" data-testid="auto-outbound-dial-capacity">
          <p className="text-sm font-medium">{t('ws.autoOutbound.monitor.dialCapacity', locale)}</p>
          <div className="grid gap-4 md:grid-cols-4">
            <MetricCard
              label={t('ws.autoOutbound.monitor.dialable', locale)}
              value={capacity.dialable}
              testId="auto-outbound-dialable"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.task', locale)}
              value={formatCapacityValue(sources?.task)}
              testId="auto-outbound-capacity-task"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.tenant', locale)}
              value={formatCapacityValue(sources?.tenant)}
              testId="auto-outbound-capacity-tenant"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.flowkit', locale)}
              value={formatCapacityValue(sources?.flowkit)}
              testId="auto-outbound-capacity-flowkit"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.trunk', locale)}
              value={formatCapacityValue(sources?.trunk)}
              testId="auto-outbound-capacity-trunk"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.batch', locale)}
              value={formatCapacityValue(sources?.batch)}
              testId="auto-outbound-capacity-batch"
            />
            <MetricCard
              label={t('ws.autoOutbound.monitor.capacity.reception', locale)}
              value={formatCapacityValue(sources?.reception)}
              testId="auto-outbound-capacity-reception"
            />
          </div>
        </div>
      )}
    </div>
  )
}

function ImportTargetsDialog({
  open,
  locale,
  fields,
  file,
  result,
  submitting,
  onFileChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  locale: ReturnType<typeof useLocaleStore.getState>['locale']
  fields: OutboundTaskField[]
  file: File | null
  result: AutoOutboundTargetImportResponse | undefined
  submitting: boolean
  onFileChange: (file: File | null) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const enabledFields = fields.filter((field) => field.enabled)
  const fieldJoin = locale === 'en' ? ', ' : '、'
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !submitting) onClose() }}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>{t('ws.autoOutbound.import.title', locale)}</DialogTitle>
          <DialogDescription>{t('ws.autoOutbound.import.desc', locale)}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <label className="block rounded-lg border border-dashed border-border p-4">
            <span className="block text-sm font-medium">{t('ws.autoOutbound.import.chooseFile', locale)}</span>
            <span className="mt-1 block text-xs text-muted-foreground">{t('ws.autoOutbound.import.fileHint', locale)}</span>
            <input
              type="file"
              accept=".xlsx,.csv"
              onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              className="mt-3 block w-full text-sm"
            />
            {file && <span className="mt-2 block text-xs text-muted-foreground">{file.name}</span>}
          </label>
          <div className="rounded-lg bg-muted/40 p-3 text-sm">
            <p className="font-medium">{t('ws.autoOutbound.import.fields', locale)}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t('ws.autoOutbound.import.required', locale, {
                fields: enabledFields.length
                  ? enabledFields.map((field) => field.name).join(fieldJoin)
                  : t('ws.autoOutbound.import.none', locale),
              })}
            </p>
          </div>
          {result && result.errors.length > 0 && (
            <div className="max-h-40 overflow-auto rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
              <ul className="space-y-1 text-xs text-destructive">
                {result.errors.slice(0, 10).map((error) => (
                  <li key={`${error.row_number}-${error.reason}`}>
                    #{error.row_number}: {error.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <DialogFooter className="pb-0">
          <button type="button" onClick={onClose} disabled={submitting} className="h-10 rounded-md border border-border px-3 text-sm disabled:opacity-50">
            {t('ws.autoOutbound.action.cancel', locale)}
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || !file}
            className="h-10 rounded-md bg-primary px-3 text-sm text-primary-foreground disabled:opacity-50"
          >
            {submitting ? t('ws.autoOutbound.import.submitting', locale) : t('ws.autoOutbound.import.submit', locale)}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function parsePhoneNumbers(value: string): string[] {
  const seen = new Set<string>()
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
}
