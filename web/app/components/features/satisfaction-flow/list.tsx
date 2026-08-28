'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  IconCopy,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Switch } from '@/components/ui/switch'
import { FlowStudioTabs } from '@/app/components/features/flow-studio-tabs'
import type { SatisfactionFlowListItem } from '@/models/satisfaction-flow'
import {
  useCopySatisfactionFlow,
  useDeleteSatisfactionFlow,
  useDisableSatisfactionFlow,
  useEnableSatisfactionFlow,
  useSatisfactionFlows,
} from '@/service/use-satisfaction-flows'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type PendingAction =
  | { kind: 'replace'; flow: SatisfactionFlowListItem; active: SatisfactionFlowListItem }
  | { kind: 'disable' | 'delete'; flow: SatisfactionFlowListItem }
  | null

function labels(values: string[], locale: string): string {
  const map: Record<string, [string, string]> = {
    auto_transfer: ['自动转入', 'Auto transfer'],
    agent_invite: ['主动邀请', 'Agent invite'],
    inbound: ['呼入', 'Inbound'],
    outbound: ['呼出', 'Outbound'],
  }
  return values.map((value) => map[value]?.[locale === 'zh' ? 0 : 1] ?? value).join('、')
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—'
}

export function SatisfactionFlowList() {
  const { locale } = useLocaleStore()
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [enabled, setEnabled] = useState<'all' | 'true' | 'false'>('all')
  const [pending, setPending] = useState<PendingAction>(null)
  const query = useSatisfactionFlows({
    page,
    per_page: 20,
    keyword: keyword || undefined,
    enabled: enabled === 'all' ? undefined : enabled === 'true',
  })
  const copy = useCopySatisfactionFlow()
  const enableFlow = useEnableSatisfactionFlow()
  const disableFlow = useDisableSatisfactionFlow()
  const deleteFlow = useDeleteSatisfactionFlow()
  const items = query.data?.items ?? []
  const active = items.find((item) => item.enabled)
  const mutating = copy.isPending || enableFlow.isPending || disableFlow.isPending || deleteFlow.isPending

  async function toggle(flow: SatisfactionFlowListItem) {
    if (flow.enabled) {
      setPending({ kind: 'disable', flow })
      return
    }
    if (active && active.id !== flow.id) {
      setPending({ kind: 'replace', flow, active })
      return
    }
    await enableFlow.mutateAsync({ id: flow.id, replaceActive: false })
    toast.success(t('sf.enabledSuccess', locale))
  }

  async function confirmAction() {
    if (!pending) return
    try {
      if (pending.kind === 'replace') {
        await enableFlow.mutateAsync({ id: pending.flow.id, replaceActive: true })
        toast.success(t('sf.enabledSuccess', locale))
      } else if (pending.kind === 'disable') {
        await disableFlow.mutateAsync(pending.flow.id)
        toast.success(t('sf.disabledSuccess', locale))
      } else {
        await deleteFlow.mutateAsync(pending.flow.id)
        toast.success(t('sf.deletedSuccess', locale))
      }
      setPending(null)
    } catch {
      toast.error(t('sf.actionFailed', locale))
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <FlowStudioTabs active="satisfaction-flows" />
        <Link
          href="/flow-studio/satisfaction-flows/new"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
        >
          <IconPlus size={16} /> {t('sf.new', locale)}
        </Link>
      </div>

      {active && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm">
          <p className="font-medium">{t('sf.active', locale)}：{active.name} · V{active.current_version_no}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t('sf.activeHint', locale)}</p>
        </div>
      )}

      <div className="flex items-center gap-3">
        <label className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
          <IconSearch size={15} className="text-muted-foreground" />
          <input
            value={keyword}
            onChange={(event) => { setKeyword(event.target.value); setPage(1) }}
            placeholder={t('sf.search', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </label>
        <select
          value={enabled}
          onChange={(event) => { setEnabled(event.target.value as typeof enabled); setPage(1) }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          <option value="all">{t('sf.statusAll', locale)}</option>
          <option value="true">{t('sf.enabled', locale)}</option>
          <option value="false">{t('sf.disabled', locale)}</option>
        </select>
      </div>

      {query.isLoading ? (
        <div className="rounded-lg border border-border p-12 text-center text-sm text-muted-foreground">{t('sf.loading', locale)}</div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-dashed border-border py-16">
          <p className="text-sm text-muted-foreground">{t('sf.empty', locale)}</p>
          <Link href="/flow-studio/satisfaction-flows/new" className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">{t('sf.new', locale)}</Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="flex h-12 items-center gap-4 bg-muted px-4 text-xs font-semibold text-muted-foreground">
            <div className="min-w-0 flex-1">{t('sf.col.name', locale)}</div>
            <div className="w-28">{t('sf.col.status', locale)}</div>
            <div className="w-40">{t('sf.col.trigger', locale)}</div>
            <div className="w-24">{t('sf.col.direction', locale)}</div>
            <div className="w-16 text-center">{t('sf.col.questions', locale)}</div>
            <div className="w-16">{t('sf.col.version', locale)}</div>
            <div className="w-40">{t('sf.col.updated', locale)}</div>
            <div className="w-28 text-center">{t('sf.col.actions', locale)}</div>
          </div>
          {items.map((flow) => (
            <div key={flow.id} className="flex min-h-16 items-center gap-4 border-t border-border px-4 text-sm">
              <div className="min-w-0 flex-1">
                <Link href={`/flow-studio/satisfaction-flows/${flow.id}`} className="font-medium hover:underline">{flow.name}</Link>
                <p className="mt-1 truncate text-xs text-muted-foreground">{flow.description || '—'}</p>
              </div>
              <div className="flex w-28 items-center gap-2">
                <Switch
                  checked={flow.enabled}
                  onCheckedChange={() => void toggle(flow)}
                  disabled={mutating}
                  aria-label={t('sf.col.status', locale)}
                />
                <span className="text-xs">{flow.enabled ? t('sf.enabled', locale) : t('sf.disabled', locale)}</span>
              </div>
              <div className="w-40 text-xs">{labels(flow.triggers, locale)}</div>
              <div className="w-24 text-xs">{labels(flow.directions, locale)}</div>
              <div className="w-16 text-center font-mono text-xs">{flow.question_count}</div>
              <div className="w-16 font-mono text-xs">V{flow.current_version_no ?? '—'}</div>
              <div className="w-40 text-xs text-muted-foreground">{formatDate(flow.updated_at)}</div>
              <div className="flex w-28 justify-center gap-3 text-muted-foreground">
                <Link href={`/flow-studio/satisfaction-flows/${flow.id}`} aria-label={t('sf.edit', locale)}><IconPencil size={17} /></Link>
                <button type="button" onClick={() => void copy.mutateAsync(flow.id).then(() => toast.success(t('sf.copiedSuccess', locale))).catch(() => toast.error(t('sf.actionFailed', locale)))} aria-label={t('sf.copy', locale)}><IconCopy size={17} /></button>
                <button type="button" disabled={flow.enabled} onClick={() => setPending({ kind: 'delete', flow })} className="disabled:opacity-30" aria-label={t('sf.delete', locale)}><IconTrash size={17} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{t('sf.total', locale, { total: query.data?.total ?? 0 })}</span>
        <div className="flex items-center gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="rounded-md border border-border px-3 py-1 disabled:opacity-40">‹</button>
          <span>{page} / {query.data?.pages || 1}</span>
          <button type="button" disabled={page >= (query.data?.pages || 1)} onClick={() => setPage((value) => value + 1)} className="rounded-md border border-border px-3 py-1 disabled:opacity-40">›</button>
        </div>
      </div>

      <ConfirmDialog
        open={pending !== null}
        title={pending?.kind === 'replace' ? t('sf.replaceTitle', locale) : pending?.kind === 'disable' ? t('sf.disableTitle', locale) : t('sf.deleteTitle', locale)}
        message={pending?.kind === 'replace' ? t('sf.replaceMessage', locale) : pending?.kind === 'disable' ? t('sf.disableMessage', locale) : t('sf.deleteMessage', locale)}
        itemName={pending?.kind === 'replace' ? `${pending.active.name} → ${pending.flow.name}` : pending?.flow.name}
        confirmLabel={pending?.kind === 'replace' ? t('sf.replace', locale) : pending?.kind === 'disable' ? t('sf.disable', locale) : t('sf.delete', locale)}
        variant={pending?.kind === 'delete' ? 'destructive' : 'default'}
        loading={mutating}
        onCancel={() => setPending(null)}
        onConfirm={confirmAction}
      />
    </div>
  )
}
