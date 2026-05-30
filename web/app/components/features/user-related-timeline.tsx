'use client'

import Link from 'next/link'
import { useMemo, useState, type ReactNode } from 'react'
import {
  IconAlertCircle,
  IconLoader2,
  IconMessageCircle,
  IconPhoneIncoming,
  IconPhoneOutgoing,
  IconRefresh,
  IconTicket,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useUserChanges } from '@/service/use-users'
import { useSessionRecords } from '@/service/use-session-records'
import { useUserRelatedTickets } from '@/service/use-tickets'
import { useCallRecords } from '@/service/use-call-center'
import { useEmployee } from '@/service/use-employees'
import { useEmployeeGroup } from '@/service/use-employee-groups'
import type { UnifiedField } from '@/models/field-definition'
import type { EntityChange } from '@/models/entity-change'
import type { SessionRecord } from '@/models/session-record'
import type { Ticket } from '@/models/ticket'
import type { CallRecordListItem } from '@/models/call-center'
import { EntityChangeCard } from '@/app/components/features/activity/entity-change-timeline'
import {
  ActivityTimeline,
  ActivityTimelineRow,
} from '@/app/components/features/ticket/activity-timeline-row'
import { SessionDetailDrawer } from '@/app/components/features/session-records/session-detail-drawer'
import {
  CallRecordDetailDrawer,
  callRecordCustomerNumber,
  callRecordServiceNumber,
  formatCallRecordDuration,
} from '@/app/components/features/call-center/call-record-detail-drawer'

type TimelineTab = 'all' | 'related'

type TimelineEvent =
  | { type: 'change'; key: string; time: string | null; change: EntityChange }
  | { type: 'ticket'; key: string; time: string | null; ticket: Ticket }
  | { type: 'session'; key: string; time: string | null; session: SessionRecord }
  | { type: 'call'; key: string; time: string | null; call: CallRecordListItem }

type UserRelatedTimelineProps = {
  userId: number
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
}

export function UserRelatedTimeline({
  userId,
  isZh,
  resolveFieldDef,
}: UserRelatedTimelineProps) {
  const [timelineTab, setTimelineTab] = useState<TimelineTab>('all')
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null)
  const [selectedCallId, setSelectedCallId] = useState<number | null>(null)

  const changesQuery = useUserChanges(userId, { page: 1, per_page: 50 }, timelineTab === 'all')
  const sessionsQuery = useSessionRecords({ visitor_id: userId, page: 1, per_page: 50 })
  const ticketsQuery = useUserRelatedTickets(userId)
  const callsQuery = useCallRecords({ user_id: userId, page: 1, per_page: 50 })

  const relatedEvents = useMemo<TimelineEvent[]>(() => {
    const tickets = (ticketsQuery.data?.items ?? []).map<TimelineEvent>((ticket) => ({
      type: 'ticket',
      key: `ticket-${ticket.id}`,
      time: ticket.created_at,
      ticket,
    }))
    const sessions = (sessionsQuery.data?.items ?? []).map<TimelineEvent>((session) => ({
      type: 'session',
      key: `session-${session.id}`,
      time: session.started_at ?? session.created_at,
      session,
    }))
    const calls = (callsQuery.data?.items ?? []).map<TimelineEvent>((call) => ({
      type: 'call',
      key: `call-${call.id}`,
      time: call.started_at,
      call,
    }))

    return sortTimelineEvents([...tickets, ...sessions, ...calls])
  }, [callsQuery.data?.items, sessionsQuery.data?.items, ticketsQuery.data?.items])

  const allEvents = useMemo<TimelineEvent[]>(() => {
    const changes = (changesQuery.data?.items ?? []).map<TimelineEvent>((change) => ({
      type: 'change',
      key: `change-${change.id}`,
      time: change.created_at,
      change,
    }))

    return sortTimelineEvents([...changes, ...relatedEvents])
  }, [changesQuery.data?.items, relatedEvents])

  const activeEvents = timelineTab === 'all' ? allEvents : relatedEvents
  const isLoading =
    sessionsQuery.isLoading ||
    ticketsQuery.isLoading ||
    callsQuery.isLoading ||
    (timelineTab === 'all' && changesQuery.isLoading)
  const isError =
    sessionsQuery.isError ||
    ticketsQuery.isError ||
    callsQuery.isError ||
    (timelineTab === 'all' && changesQuery.isError)

  const retry = () => {
    void sessionsQuery.refetch()
    void ticketsQuery.refetch()
    void callsQuery.refetch()
    if (timelineTab === 'all') void changesQuery.refetch()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-l border-border bg-white">
      <div className="flex shrink-0 border-b border-border bg-white px-6">
        <TimelineTabButton
          active={timelineTab === 'all'}
          onClick={() => setTimelineTab('all')}
        >
          {isZh ? '全部' : 'All'}
        </TimelineTabButton>
        <TimelineTabButton
          active={timelineTab === 'related'}
          onClick={() => setTimelineTab('related')}
        >
          {isZh ? '相关记录' : 'Related'}
        </TimelineTabButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-white p-6">
        {isLoading ? (
          <TimelineState
            icon={<IconLoader2 size={22} className="animate-spin" />}
            text={isZh ? '加载动态中...' : 'Loading activity...'}
          />
        ) : isError ? (
          <TimelineState
            icon={<IconAlertCircle size={22} />}
            text={isZh ? '相关记录加载失败' : 'Failed to load related records'}
            actionLabel={isZh ? '重试' : 'Retry'}
            onAction={retry}
          />
        ) : activeEvents.length === 0 ? (
          <TimelineState
            icon={timelineTab === 'related' ? <IconTicket size={32} strokeWidth={1.5} /> : undefined}
            text={
              timelineTab === 'related'
                ? isZh ? '暂无会话、工单与通话记录' : 'No sessions, tickets, or calls yet'
                : isZh ? '暂无动态' : 'No activity yet'
            }
          />
        ) : (
          <ActivityTimeline
            railTailClassName="bg-white"
            railTopClassName={getTimelineRailTopClassName(activeEvents[0])}
          >
            {activeEvents.map((event) => (
              <ActivityTimelineRow
                key={event.key}
                dotOffsetClassName={getTimelineDotOffsetClassName(event)}
                railTailTopClassName={getTimelineRailTailTopClassName(event)}
              >
                <TimelineEventCard
                  event={event}
                  isZh={isZh}
                  resolveFieldDef={resolveFieldDef}
                  onOpenSession={setSelectedSessionId}
                  onOpenCall={setSelectedCallId}
                />
              </ActivityTimelineRow>
            ))}
          </ActivityTimeline>
        )}
      </div>

      {selectedSessionId != null ? (
        <SessionDetailDrawer
          recordId={selectedSessionId}
          onClose={() => setSelectedSessionId(null)}
        />
      ) : null}
      {selectedCallId != null ? (
        <CallRecordDetailDrawer
          recordId={selectedCallId}
          onClose={() => setSelectedCallId(null)}
        />
      ) : null}
    </div>
  )
}

function TimelineTabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative px-4 py-3 text-sm font-medium transition-colors',
        active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground/80',
      )}
    >
      {children}
      {active ? (
        <span className="absolute bottom-0 left-4 right-4 h-0.5 rounded-full bg-primary" />
      ) : null}
    </button>
  )
}

function TimelineEventCard({
  event,
  isZh,
  resolveFieldDef,
  onOpenSession,
  onOpenCall,
}: {
  event: TimelineEvent
  isZh: boolean
  resolveFieldDef: (fieldKey: string) => UnifiedField | undefined
  onOpenSession: (sessionId: number) => void
  onOpenCall: (callId: number) => void
}) {
  if (event.type === 'change') {
    return (
      <EntityChangeCard
        change={event.change}
        isZh={isZh}
        resolveFieldDef={resolveFieldDef}
      />
    )
  }

  if (event.type === 'ticket') {
    return <TicketTimelineCard ticket={event.ticket} isZh={isZh} />
  }

  if (event.type === 'call') {
    return (
      <CallTimelineCard
        record={event.call}
        isZh={isZh}
        onOpen={() => onOpenCall(event.call.id)}
      />
    )
  }

  return (
    <SessionTimelineCard
      session={event.session}
      isZh={isZh}
      onOpen={() => onOpenSession(event.session.id)}
    />
  )
}

function CallTimelineCard({
  record,
  isZh,
  onOpen,
}: {
  record: CallRecordListItem
  isZh: boolean
  onOpen: () => void
}) {
  const DirectionIcon = record.direction === 'inbound' ? IconPhoneIncoming : IconPhoneOutgoing
  const directionLabel = record.direction === 'inbound'
    ? (isZh ? '呼入' : 'Inbound')
    : (isZh ? '呼出' : 'Outbound')
  const customerNumber = callRecordCustomerNumber(record)
  const serviceNumber = callRecordServiceNumber(record)

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-lg bg-white px-4 py-3.5 text-left transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
            <DirectionIcon size={15} />
          </span>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5 text-[13px] text-foreground">
              <span>{isZh ? '通话' : 'Call'}</span>
              <span className="max-w-[220px] truncate font-medium text-primary">
                {record.call_id}
              </span>
            </div>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {isZh ? '用户号码' : 'User number'}: {customerNumber || (isZh ? '未知号码' : 'Unknown')}
            </p>
          </div>
        </div>
        <time className="shrink-0 text-xs text-muted-foreground" dateTime={record.started_at}>
          {formatTimelineTime(record.started_at, isZh)}
        </time>
      </div>
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
        <TimelineMeta label={isZh ? '类型' : 'Type'}>
          <span
            className={cn(
              'inline-flex items-center rounded px-1.5 py-0.5',
              record.direction === 'inbound'
                ? 'bg-blue-50 text-blue-700'
                : 'bg-green-50 text-green-700',
            )}
          >
            {directionLabel}
          </span>
        </TimelineMeta>
        <TimelineMeta label={isZh ? '接待客服' : 'Agent'}>
          <span className="text-foreground">{record.agent_name || '-'}</span>
        </TimelineMeta>
        <TimelineMeta label={isZh ? '时长' : 'Duration'}>
          <span className="text-foreground">{formatCallRecordDuration(record.talk_duration_ms)}</span>
        </TimelineMeta>
      </div>
      <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <TimelineMeta label={isZh ? '服务号码' : 'Service number'}>
          <span className="text-foreground">{serviceNumber || '-'}</span>
        </TimelineMeta>
        <TimelineMeta label={isZh ? '状态' : 'Status'}>
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-foreground">
            {record.state || '-'}
          </span>
        </TimelineMeta>
      </div>
    </button>
  )
}

function TicketTimelineCard({ ticket, isZh }: { ticket: Ticket; isZh: boolean }) {
  return (
    <div className="rounded-lg bg-white px-4 py-3.5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
            <IconTicket size={15} />
          </span>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5 text-[13px] text-foreground">
              <span>{isZh ? '创建工单' : 'Ticket created'}</span>
              <Link
                href={`/workspace/tickets/${ticket.id}?from=list`}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                #{ticket.id}
              </Link>
              {ticket.ticket_number ? (
                <span className="truncate text-muted-foreground">({ticket.ticket_number})</span>
              ) : null}
            </div>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {ticket.title?.trim() || '-'}
            </p>
          </div>
        </div>
        <time className="shrink-0 text-xs text-muted-foreground" dateTime={ticket.created_at}>
          {formatTimelineTime(ticket.created_at, isZh)}
        </time>
      </div>
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
        <TimelineMeta label={isZh ? '负责组' : 'Group'}>
          <EmployeeGroupName groupId={ticket.assignee_group_id} isZh={isZh} />
        </TimelineMeta>
        <TimelineMeta label={isZh ? '负责人' : 'Agent'}>
          <EmployeeName employeeId={ticket.agent_id} isZh={isZh} />
        </TimelineMeta>
        <TimelineMeta label={isZh ? '状态' : 'Status'}>
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-foreground">
            {ticket.status || '-'}
          </span>
        </TimelineMeta>
      </div>
    </div>
  )
}

function SessionTimelineCard({
  session,
  isZh,
  onOpen,
}: {
  session: SessionRecord
  isZh: boolean
  onOpen: () => void
}) {
  const eventTime = session.started_at ?? session.created_at
  const agentName = session.agent?.display_name || session.agent?.name || '-'
  const channelName = session.channel?.channel_type || '-'
  const sessionCode = session.share_code || session.public_id

  return (
    <div className="rounded-lg bg-white px-4 py-3.5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
            <IconMessageCircle size={15} />
          </span>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5 text-[13px] text-foreground">
              <span>{isZh ? '会话' : 'Session'}</span>
              <button
                type="button"
                onClick={onOpen}
                className="max-w-[220px] truncate align-bottom font-medium text-primary underline-offset-2 hover:underline"
                title={sessionCode}
              >
                {sessionCode}
              </button>
            </div>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {isZh ? '接待客服' : 'Agent'}: {agentName}
            </p>
          </div>
        </div>
        {eventTime ? (
          <time className="shrink-0 text-xs text-muted-foreground" dateTime={eventTime}>
            {formatTimelineTime(eventTime, isZh)}
          </time>
        ) : null}
      </div>
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <TimelineMeta label={isZh ? '渠道类型' : 'Channel'}>
          <span className="text-foreground">{channelName}</span>
        </TimelineMeta>
        <TimelineMeta label={isZh ? '会话状态' : 'Status'}>
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-foreground">
            {session.status || '-'}
          </span>
        </TimelineMeta>
      </div>
    </div>
  )
}

function TimelineMeta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <span className="mr-1">{label}:</span>
      {children}
    </div>
  )
}

function EmployeeName({
  employeeId,
  isZh,
}: {
  employeeId: number | null
  isZh: boolean
}) {
  const { data: employee } = useEmployee(employeeId ?? 0)

  if (!employeeId) return <span className="text-foreground">-</span>

  return (
    <span className="text-foreground">
      {employee?.nickname || employee?.name || employee?.username || (isZh ? `员工 #${employeeId}` : `Employee #${employeeId}`)}
    </span>
  )
}

function EmployeeGroupName({
  groupId,
  isZh,
}: {
  groupId: number | null
  isZh: boolean
}) {
  const { data: group } = useEmployeeGroup(groupId ?? 0)

  if (!groupId) return <span className="text-foreground">-</span>

  return (
    <span className="text-foreground">
      {group?.name || (isZh ? `负责组 #${groupId}` : `Group #${groupId}`)}
    </span>
  )
}

function TimelineState({
  icon,
  text,
  actionLabel,
  onAction,
}: {
  icon?: ReactNode
  text: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-muted-foreground">
      {icon}
      <p className="text-sm">{text}</p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-1 inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
        >
          <IconRefresh size={14} />
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}

function sortTimelineEvents(events: TimelineEvent[]): TimelineEvent[] {
  return [...events].sort((a, b) => getTimeValue(b.time) - getTimeValue(a.time))
}

function getTimelineDotOffsetClassName(event: TimelineEvent): string {
  return event.type === 'change' ? 'pt-[18px]' : 'pt-[24px]'
}

function getTimelineRailTopClassName(event: TimelineEvent | undefined): string {
  if (!event) return 'top-[22px]'
  return event.type === 'change' ? 'top-[22px]' : 'top-[28px]'
}

function getTimelineRailTailTopClassName(event: TimelineEvent): string {
  return event.type === 'change' ? 'top-[26px]' : 'top-[32px]'
}

function getTimeValue(value: string | null): number {
  if (!value) return Number.NEGATIVE_INFINITY
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time
}

function formatTimelineTime(value: string, isZh: boolean): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}
