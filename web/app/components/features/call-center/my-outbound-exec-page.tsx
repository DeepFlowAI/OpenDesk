'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconArrowLeft } from '@tabler/icons-react'

import { EmptyState, formatDateTime } from '@/app/components/features/engagement/outbound-task-ui'
import { OutboundScriptRunner } from '@/app/components/features/engagement/outbound-script-runner'
import { useCallCenterRuntime } from '@/context/call-center-runtime'
import { useLocaleStore } from '@/context/locale-store'
import { normalizeDialPhone } from '@/lib/call-workspace-view'
import {
  type MyOutboundTaskItem,
  type OutboundTarget,
  type OutboundTargetStatus,
} from '@/models/outbound-task'
import { useMyOutboundTargets, useMyOutboundTargetScript } from '@/service/use-outbound-tasks'
import { t } from '@/utils/i18n'
import { updateOutboundTargetDraft } from './outbound-task-fields'
import { ExecTargetStatusBadge, ExecTaskStatusBadge } from './my-outbound-badges'
import { MyOutboundTargetPanel } from './my-outbound-target-panel'
import { MyOutboundWrapUp } from './my-outbound-wrap-up'

const TARGET_FILTER_STATUSES: OutboundTargetStatus[] = ['pending', 'redial', 'completed']

export function MyOutboundExecPage({
  task,
  onBack,
  onStartCall,
  onOpenScreenPop,
}: {
  task: MyOutboundTaskItem
  onBack: () => void
  onStartCall?: (phone: string, taskId: number) => void | Promise<void>
  onOpenScreenPop?: (target: OutboundTarget) => void
}) {
  const { locale } = useLocaleStore()
  const { phase, incoming } = useCallCenterRuntime()
  const [status, setStatus] = useState<'' | OutboundTargetStatus>('')
  const { data, isLoading } = useMyOutboundTargets({ page: 1, per_page: 100, task_id: task.id, status })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [fieldDrafts, setFieldDrafts] = useState<Record<number, Record<string, unknown>>>({})
  const [scriptOpen, setScriptOpen] = useState(false)
  const selectedTarget = useMemo(
    () => data?.items.find((item) => item.id === selectedId) ?? data?.items[0] ?? null,
    [data?.items, selectedId],
  )
  // The wrap-up screen replaces the exec panel only while the just-ended call
  // belongs to the selected target; picking another target exits it.
  const wrapUpActive =
    phase === 'wrap_up' &&
    incoming?.direction === 'outbound' &&
    selectedTarget != null &&
    normalizeDialPhone(selectedTarget.phone_number) === normalizeDialPhone(incoming.to)
  const hasScript = Boolean(selectedTarget?.task?.has_script)
  const scriptQuery = useMyOutboundTargetScript(selectedTarget?.id ?? 0, scriptOpen && hasScript)
  const progressPct = task.my_total ? Math.round((task.my_completed / task.my_total) * 100) : 0

  useEffect(() => {
    if (!selectedTarget?.task?.has_script) setScriptOpen(false)
  }, [selectedTarget?.id, selectedTarget?.task?.has_script])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-background px-5 py-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted"
        >
          <IconArrowLeft size={13} />
          {t('ws.outboundExec.exec.back', locale)}
        </button>
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-sm font-semibold">{task.name}</h1>
          <ExecTaskStatusBadge status={task.status} />
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <span>
            {t('ws.outboundExec.exec.progress', locale, {
              completed: task.my_completed,
              total: task.my_total,
              percent: progressPct,
            })}
          </span>
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[320px] shrink-0 flex-col border-r border-border bg-background">
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">{task.name}</h2>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as '' | OutboundTargetStatus)}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs text-muted-foreground"
            >
              <option value="">{t('ws.outboundExec.targetList.allStatus', locale)}</option>
              {TARGET_FILTER_STATUSES.map((value) => (
                <option key={value} value={value}>{t(`ws.outboundExec.status.target.${value}`, locale)}</option>
              ))}
            </select>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {isLoading ? (
              <p className="p-2 text-sm text-muted-foreground">{t('ws.outboundExec.targetList.loading', locale)}</p>
            ) : (data?.items.length ?? 0) === 0 ? (
              <EmptyState
                title={t('ws.outboundExec.targetList.empty', locale)}
                action={
                  <button
                    type="button"
                    onClick={onBack}
                    className="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                  >
                    {t('ws.outboundExec.exec.back', locale)}
                  </button>
                }
              />
            ) : (
              <div className="space-y-2">
                {data?.items.map((target) => (
                  <button
                    key={target.id}
                    type="button"
                    onClick={() => setSelectedId(target.id)}
                    className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedTarget?.id === target.id ? 'border-primary/60 bg-muted/50' : 'border-border bg-card hover:bg-muted/40'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{target.user_name || target.phone_number}</span>
                      <ExecTargetStatusBadge status={target.status} />
                    </div>
                    {target.user_name ? (
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground">{target.phone_number}</p>
                    ) : null}
                    <p className="mt-1.5 text-xs text-muted-foreground">
                      {target.last_called_at
                        ? t('ws.outboundExec.targetList.lastCall', locale, {
                            time: formatDateTime(target.last_called_at),
                            result: target.last_call_result || '-',
                            count: target.call_count,
                          })
                        : t('ws.outboundExec.targetList.noCallYet', locale)}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
        {wrapUpActive && selectedTarget ? (
          <main className="min-h-0 flex-1 overflow-hidden bg-muted/40">
            <MyOutboundWrapUp
              key={`${selectedTarget.id}-${incoming?.call_id ?? ''}`}
              target={selectedTarget}
              fieldValues={fieldDrafts[selectedTarget.id] ?? selectedTarget.field_values ?? {}}
              onFieldChange={(fieldKey, value) => {
                setFieldDrafts((current) => updateOutboundTargetDraft(
                  current,
                  selectedTarget.id,
                  selectedTarget.field_values ?? {},
                  fieldKey,
                  value,
                ))
              }}
              onSubmitted={() => {
                setFieldDrafts((current) => {
                  const next = { ...current }
                  delete next[selectedTarget.id]
                  return next
                })
              }}
              onOpenScreenPop={onOpenScreenPop}
            />
          </main>
        ) : (
        <main className="min-h-0 flex-1 overflow-auto bg-muted/40 p-5">
          {selectedTarget ? (
            <MyOutboundTargetPanel
              key={selectedTarget.id}
              target={selectedTarget}
              taskStatus={task.status}
              fieldValues={fieldDrafts[selectedTarget.id] ?? selectedTarget.field_values ?? {}}
              hasFieldDraft={fieldDrafts[selectedTarget.id] !== undefined}
              onFieldChange={(fieldKey, value) => {
                setFieldDrafts((current) => updateOutboundTargetDraft(
                  current,
                  selectedTarget.id,
                  selectedTarget.field_values ?? {},
                  fieldKey,
                  value,
                ))
              }}
              onFieldsSaved={() => {
                setFieldDrafts((current) => {
                  const next = { ...current }
                  delete next[selectedTarget.id]
                  return next
                })
              }}
              onStartCall={onStartCall}
              onOpenScript={() => setScriptOpen(true)}
              onOpenScreenPop={onOpenScreenPop}
            />
          ) : (
            !isLoading && <EmptyState title={t('ws.outboundExec.targetList.empty', locale)} />
          )}
        </main>
        )}
        {scriptOpen && selectedTarget?.task?.has_script && (
          scriptQuery.data ? (
            <OutboundScriptRunner
              open
              script={scriptQuery.data}
              subtitle={selectedTarget.task?.name}
              sessionKey={selectedTarget.id}
              variant="panel"
              onClose={() => setScriptOpen(false)}
            />
          ) : (
            <aside className="flex h-full w-[520px] shrink-0 flex-col items-center justify-center gap-3 border-l border-border bg-background">
              {scriptQuery.isError ? (
                <>
                  <p className="text-sm text-destructive">{t('ws.outboundExec.script.loadFailed', locale)}</p>
                  <div className="flex items-center gap-3">
                    <button type="button" onClick={() => void scriptQuery.refetch()} className="rounded-md border border-border px-3 py-1.5 text-sm">{t('ws.outboundExec.script.retry', locale)}</button>
                    <button type="button" onClick={() => setScriptOpen(false)} className="text-sm text-muted-foreground">{t('ws.outboundExec.script.close', locale)}</button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t('ws.outboundExec.script.loading', locale)}</p>
              )}
            </aside>
          )
        )}
      </div>
    </div>
  )
}
