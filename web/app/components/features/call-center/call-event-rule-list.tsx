'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconChevronLeft,
  IconChevronRight,
  IconPencil,
  IconPlus,
  IconSearch,
  IconTrash,
  IconWebhook,
} from '@tabler/icons-react'
import { toast } from 'sonner'

import { CallIntegrationTabs } from '@/app/components/features/call-center/call-integration-tabs'
import {
  CALL_EVENT_LABELS,
  describeScope,
  pick,
} from '@/app/components/features/call-center/call-event-rule-catalog'
import {
  permissionDeniedText,
  readCallEventRuleError,
} from '@/app/components/features/call-center/call-event-rule-errors'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import type { CallEventRule } from '@/models/call-event-subscription'
import {
  useCallEventRules,
  useDeleteCallEventRule,
  useToggleCallEventRule,
} from '@/service/use-call-event-subscriptions'

type StatusFilter = '' | 'active' | 'inactive'
type PendingAction = { action: 'enable' | 'disable' | 'delete'; rule: CallEventRule }

const PER_PAGE = 20
const NEW_PATH = '/call-center/integrations/event-subscriptions/new'

function formatDateTime(value: string, isZh: boolean) {
  try {
    return new Date(value).toLocaleString(isZh ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

export function CallEventRuleList() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const [search, setSearch] = useState('')
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState<PendingAction | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setKeyword(search.trim())
      setPage(1)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search])

  const query = useCallEventRules({
    page,
    per_page: PER_PAGE,
    ...(keyword ? { q: keyword } : {}),
    ...(status ? { status } : {}),
  })
  const toggle = useToggleCallEventRule()
  const remove = useDeleteCallEventRule()
  const busy = toggle.isPending || remove.isPending

  const items = query.data?.items ?? []
  const filtered = Boolean(keyword || status)
  const limitReached = (query.data?.tenant_rule_count ?? 0) >= (query.data?.max_rules ?? 10)
  const pages = Math.max(query.data?.pages ?? 1, 1)

  const resetFilters = () => {
    setSearch('')
    setKeyword('')
    setStatus('')
    setPage(1)
  }

  const confirm = async () => {
    if (!pending) return
    const { action, rule } = pending
    try {
      if (action === 'delete') {
        await remove.mutateAsync(rule.public_id)
        toast.success(isZh ? '规则已删除' : 'Rule deleted')
        if (items.length === 1 && page > 1) setPage(page - 1)
      } else {
        await toggle.mutateAsync({ id: rule.public_id, enabled: action === 'enable' })
        toast.success(
          action === 'enable'
            ? (isZh ? '规则已启用' : 'Rule enabled')
            : (isZh ? '规则已停用' : 'Rule disabled'),
        )
      }
      setPending(null)
    } catch (error) {
      const info = await readCallEventRuleError(error)
      if (info.status === 403) toast.error(permissionDeniedText(isZh))
      else if (info.status === 404) {
        toast.error(isZh ? '规则不存在或已被删除' : 'Rule not found')
        setPending(null)
        void query.refetch()
      } else toast.error(isZh ? '操作失败，请重试' : 'Operation failed. Try again')
    }
  }

  const dialog = pending
    ? pending.action === 'delete'
      ? {
          title: isZh ? '删除通话事件订阅规则' : 'Delete rule',
          message: isZh
            ? '删除后不再推送新的通话事件，已生成的投递会继续完成。删除后不可恢复。'
            : 'Deleted rules stop new call events. Pending deliveries will still complete. This cannot be undone.',
          confirmLabel: isZh ? '确定删除' : 'Delete',
          variant: 'destructive' as const,
        }
      : pending.action === 'disable'
        ? {
            title: isZh ? '停用通话事件订阅规则' : 'Disable rule',
            message: isZh
              ? '停用后不再推送新的通话事件，重新启用不会回补停用期间的事件。'
              : 'New call events stop being sent. Re-enabling does not backfill events from the disabled period.',
            confirmLabel: isZh ? '停用' : 'Disable',
            variant: 'destructive' as const,
          }
        : {
            title: isZh ? '启用通话事件订阅规则' : 'Enable rule',
            message: isZh
              ? '启用后，命中规则的新通话事件会推送到所选订阅接口。'
              : 'New call events that match this rule will be sent to the selected subscription.',
            confirmLabel: isZh ? '启用' : 'Enable',
            variant: 'default' as const,
          }
    : null

  return (
    <div className="flex flex-col gap-6">
      <CallIntegrationTabs />
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold text-foreground">{isZh ? '事件订阅' : 'Event subscriptions'}</h1>
        <span title={limitReached ? (isZh ? '最多创建 10 条规则' : 'You can create up to 10 rules') : undefined}>
          <button
            type="button"
            disabled={limitReached}
            onClick={() => router.push(NEW_PATH)}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconPlus size={18} />
            {isZh ? '新建规则' : 'New rule'}
          </button>
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex h-9 w-[280px] items-center gap-2 rounded-lg border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input
            type="text"
            value={search}
            maxLength={50}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={isZh ? '搜索规则名称' : 'Search rules'}
            aria-label={isZh ? '搜索规则名称' : 'Search rules'}
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
        <label htmlFor="call-event-rule-status" className="text-sm font-medium text-foreground/80">
          {isZh ? '状态' : 'Status'}
        </label>
        <select
          id="call-event-rule-status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as StatusFilter)
            setPage(1)
          }}
          className="h-9 w-[140px] rounded-lg border border-border bg-background px-3 text-sm"
        >
          <option value="">{isZh ? '全部' : 'All'}</option>
          <option value="active">{isZh ? '启用中' : 'Enabled'}</option>
          <option value="inactive">{isZh ? '已停用' : 'Disabled'}</option>
        </select>
      </div>

      {query.isLoading ? (
        <div className="overflow-hidden rounded-lg border border-border">
          <div className="h-14 bg-muted" />
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="flex h-14 items-center gap-4 border-t border-border px-6">
              <div className="h-4 flex-1 animate-pulse rounded bg-muted" />
              <div className="h-4 w-[168px] animate-pulse rounded bg-muted" />
              <div className="h-4 w-[88px] animate-pulse rounded bg-muted" />
              <div className="h-4 w-[168px] animate-pulse rounded bg-muted" />
              <div className="h-4 w-[72px] animate-pulse rounded bg-muted" />
              <div className="h-4 w-[108px] animate-pulse rounded bg-muted" />
              <div className="h-4 w-[56px] animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
      ) : query.isError ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <p className="text-sm text-muted-foreground">{isZh ? '加载失败，请重试' : 'Failed to load. Try again.'}</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
          >
            {isZh ? '重试' : 'Retry'}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-muted">
            <IconWebhook size={22} className="text-muted-foreground" />
          </div>
          {filtered ? (
            <>
              <p className="text-sm text-muted-foreground">{isZh ? '未找到匹配的规则' : 'No matching rules'}</p>
              <button
                type="button"
                onClick={resetFilters}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
              >
                {isZh ? '重置筛选' : 'Reset filters'}
              </button>
            </>
          ) : (
            <>
              <div className="text-center">
                <p className="text-sm font-medium text-foreground">
                  {isZh ? '暂无通话事件订阅规则' : 'No call event subscription rules'}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {isZh ? '将通话事件推送到已配置的订阅接口' : 'Send call events to configured subscriptions'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => router.push(NEW_PATH)}
                className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground"
              >
                <IconPlus size={18} />
                {isZh ? '新建规则' : 'New rule'}
              </button>
            </>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-14 items-center gap-4 bg-muted px-6 text-sm font-semibold text-foreground/80">
              <span className="min-w-0 flex-1">{isZh ? '规则名称' : 'Rule'}</span>
              <span className="w-[168px] shrink-0">{isZh ? '订阅接口' : 'Subscription'}</span>
              <span className="w-[88px] shrink-0">{isZh ? '事件' : 'Events'}</span>
              <span className="w-[168px] shrink-0">{isZh ? '通话范围' : 'Scope'}</span>
              <span className="w-[72px] shrink-0">{isZh ? '状态' : 'Status'}</span>
              <span className="w-[108px] shrink-0">{isZh ? '更新时间' : 'Updated'}</span>
              <span className="w-[56px] shrink-0 text-right">{isZh ? '操作' : 'Actions'}</span>
            </div>
            {items.map((rule) => {
              const editPath = `/call-center/integrations/event-subscriptions/${rule.public_id}`
              const scope = describeScope(rule.directions, rule.call_sources, isZh)
              const eventNames = rule.event_types
                .map((code) => (CALL_EVENT_LABELS[code] ? pick(CALL_EVENT_LABELS[code], isZh) : code))
                .join('\n')
              return (
                <div key={rule.public_id} className="flex h-14 items-center gap-4 border-t border-border px-6 text-sm">
                  <span className="min-w-0 flex-1 truncate text-foreground" title={rule.name}>{rule.name}</span>
                  <span className="flex w-[168px] min-w-0 shrink-0 items-center gap-2">
                    <span className="truncate" title={rule.subscription.name}>{rule.subscription.name}</span>
                    {!rule.subscription.is_active && (
                      <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {isZh ? '已停用' : 'Disabled'}
                      </span>
                    )}
                  </span>
                  <span className="w-[88px] shrink-0 text-muted-foreground" title={eventNames}>
                    {isZh ? `${rule.event_types.length} 个事件` : `${rule.event_types.length} event${rule.event_types.length === 1 ? '' : 's'}`}
                  </span>
                  <span className="w-[168px] shrink-0 truncate text-muted-foreground" title={scope.detail}>
                    {scope.summary}
                  </span>
                  <span className="flex w-[72px] shrink-0">
                    <Switch
                      checked={rule.is_active}
                      disabled={busy}
                      aria-label={isZh ? `切换规则状态：${rule.name}` : `Toggle rule: ${rule.name}`}
                      onCheckedChange={(checked) => setPending({ action: checked ? 'enable' : 'disable', rule })}
                    />
                  </span>
                  <span className="w-[108px] shrink-0 text-muted-foreground">{formatDateTime(rule.updated_at, isZh)}</span>
                  <span className="flex w-[56px] shrink-0 items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => router.push(editPath)}
                      className="text-foreground/80 transition-colors hover:text-foreground"
                      aria-label={isZh ? '编辑' : 'Edit'}
                      title={isZh ? '编辑' : 'Edit'}
                    >
                      <IconPencil size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setPending({ action: 'delete', rule })}
                      className="text-destructive transition-colors hover:text-destructive/80"
                      aria-label={isZh ? '删除' : 'Delete'}
                      title={isZh ? '删除' : 'Delete'}
                    >
                      <IconTrash size={18} />
                    </button>
                  </span>
                </div>
              )
            })}
          </div>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>{isZh ? `共 ${query.data?.total ?? 0} 条规则` : `${query.data?.total ?? 0} rules`}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label={isZh ? '上一页' : 'Previous page'}
                className="grid h-8 w-8 place-items-center rounded-lg border border-border disabled:opacity-40"
                disabled={page <= 1}
                onClick={() => setPage((value) => value - 1)}
              >
                <IconChevronLeft size={16} />
              </button>
              <span>{page} / {pages}</span>
              <button
                type="button"
                aria-label={isZh ? '下一页' : 'Next page'}
                className="grid h-8 w-8 place-items-center rounded-lg border border-border disabled:opacity-40"
                disabled={page >= pages}
                onClick={() => setPage((value) => value + 1)}
              >
                <IconChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={dialog?.title ?? ''}
        message={dialog?.message}
        itemName={pending ? `${isZh ? '规则名称：' : 'Rule: '}${pending.rule.name}` : undefined}
        itemDescription={pending ? `${isZh ? '订阅接口：' : 'Subscription: '}${pending.rule.subscription.name}` : undefined}
        confirmLabel={dialog?.confirmLabel}
        cancelLabel={isZh ? '取消' : 'Cancel'}
        variant={dialog?.variant}
        loading={busy}
        onCancel={() => setPending(null)}
        onConfirm={confirm}
      />
    </div>
  )
}
