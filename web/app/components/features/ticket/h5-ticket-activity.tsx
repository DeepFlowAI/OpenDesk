'use client'

import { useMemo, useState } from 'react'

import { ActivityActorAvatar } from '@/app/components/features/ticket/activity-actor-avatar'
import { TicketCommentThread } from '@/app/components/features/ticket/ticket-comment-thread'
import { cn } from '@/lib/utils'
import type { TicketChange, TicketChangeValue } from '@/models/ticket'
import { useTicketChanges } from '@/service/use-tickets'

type ActivityTab = 'comments' | 'changes' | 'all'

export function H5TicketActivity({ ticketId, canComment, isZh }: { ticketId: number; canComment: boolean; isZh: boolean }) {
  const [tab, setTab] = useState<ActivityTab>('comments')
  const changeParams = useMemo(() => ({ page: 1, per_page: 50 }), [])
  const changesQuery = useTicketChanges(ticketId, changeParams, tab !== 'comments')
  const changes = changesQuery.data?.items ?? []

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 gap-2 overflow-x-auto px-4 py-3">
        {(['comments', 'changes', 'all'] as const).map((value) => (
          <button key={value} type="button" onClick={() => setTab(value)} className={cn('h-8 shrink-0 rounded-full px-3 text-xs', tab === value ? 'bg-primary text-primary-foreground' : 'bg-secondary')}>
            {value === 'comments' ? (isZh ? '评论' : 'Comments') : value === 'changes' ? (isZh ? '变更记录' : 'Changes') : (isZh ? '全部' : 'All')}
          </button>
        ))}
      </div>
      {tab === 'changes' ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          {changesQuery.isLoading ? <ActivityHint text={isZh ? '加载中…' : 'Loading…'} />
            : changesQuery.isError ? <ActivityHint text={isZh ? '加载失败，请重试' : 'Failed to load. Please try again'} />
              : !changes.length ? <ActivityHint text={isZh ? '暂无变更记录' : 'No changes yet'} />
                : <div className="flex flex-col divide-y divide-border">{changes.map((change) => <H5TicketChangeCard key={change.id} change={change} isZh={isZh} />)}</div>}
        </div>
      ) : (
        <TicketCommentThread
          ticketId={ticketId}
          isZh={isZh}
          mergeWithChanges={tab === 'all'}
          changes={changes}
          changesLoading={changesQuery.isLoading}
          changesError={changesQuery.isError}
          renderChange={(change) => <H5TicketChangeCard change={change} isZh={isZh} />}
          showComposer={tab === 'comments' && canComment}
          emptyText={tab === 'comments' ? (isZh ? '暂无评论' : 'No comments yet') : (isZh ? '暂无动态记录' : 'No activity yet')}
          className="min-h-0 flex-1 [&>div:first-child]:px-4"
        />
      )}
    </div>
  )
}

function H5TicketChangeCard({ change, isZh }: { change: TicketChange; isZh: boolean }) {
  const author = change.actor_name || (isZh ? '系统' : 'System')
  const entries = change.entries?.length ? change.entries : [{ field_label: change.field_label, old_value: change.old_value, new_value: change.new_value }]
  return (
    <article className="py-4">
      <div className="mb-2 flex items-center gap-2">
        <ActivityActorAvatar name={author} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{author}</span>
        <time className="text-[11px] text-muted-foreground" dateTime={change.created_at}>{new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(change.created_at))}</time>
      </div>
      <div className="flex flex-col gap-1.5 pl-9 text-sm">
        {change.field_key === '__create__' ? <p>{isZh ? '创建了工单' : 'Created the ticket'}</p> : entries.map((entry, index) => (
          <p key={`${entry.field_label}-${index}`} className="break-words">
            <span className="font-medium">{entry.field_label}</span>
            <span className="text-muted-foreground">：{formatValue(entry.old_value)} → {formatValue(entry.new_value)}</span>
          </p>
        ))}
      </div>
    </article>
  )
}

function formatValue(value: TicketChangeValue): string {
  if (value == null || value === '') return '—'
  if (Array.isArray(value)) return value.map(String).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function ActivityHint({ text }: { text: string }) {
  return <div className="flex h-full items-center justify-center py-12 text-sm text-muted-foreground">{text}</div>
}
