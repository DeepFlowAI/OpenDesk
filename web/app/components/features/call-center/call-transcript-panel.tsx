'use client'

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'

import { useLocaleStore } from '@/context/locale-store'
import { useSocketStore } from '@/context/socket-store'
import {
  useBotTranscript,
  useCallTranscript,
  useRecordBotTranscript,
} from '@/service/use-call-center'
import { useSystemSettings } from '@/service/use-system-settings'
import type { BotTranscriptResponse } from '@/models/call-center'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { TranscriptBubbles, type TranscriptBubble } from './transcript-bubbles'

/**
 * Live transcript of the bridged voice call, shown once an agent picks up.
 *
 * Renders the visitor↔agent dialogue in real time from `cc.transcript`
 * Socket.IO events. Text is held in component state only — switching calls or
 * hanging up clears it. Persisted lines are shown afterwards from history via
 * {@link CallTranscriptHistory}.
 */
type TranscriptRole = 'user' | 'agent'

type TranscriptEvent = {
  call_id: string
  role: TranscriptRole
  text: string
  final: boolean
  seq?: number | null
}

/**
 * Apply one live ASR caption to the bubble list.
 *
 * At most one open (final === false) bubble exists per role. Partials for that
 * role only grow the text (never shrink) so ASR revisions mid-utterance do not
 * flicker; a matching final replaces the open bubble in place. A shorter
 * partial that is NOT a prefix of the open text is a new utterance (the
 * previous final got lost) — keep the old line and append a fresh bubble
 * instead of replacing its text, so the transcript only ever grows.
 */
export function applyTranscriptEvent(
  prev: TranscriptBubble[],
  event: { role: TranscriptRole; text: string; final: boolean },
): TranscriptBubble[] {
  let openIdx = -1
  for (let i = prev.length - 1; i >= 0; i--) {
    if (prev[i].role === event.role && prev[i].final === false) {
      openIdx = i
      break
    }
  }

  if (openIdx >= 0) {
    const open = prev[openIdx]
    if (
      !event.final &&
      event.text.length < open.text.length &&
      !open.text.startsWith(event.text)
    ) {
      const finalized: TranscriptBubble = { ...open, final: true }
      let maxId = 0
      for (const bubble of prev) {
        if (bubble.id > maxId) maxId = bubble.id
      }
      return [
        ...prev.slice(0, openIdx),
        finalized,
        ...prev.slice(openIdx + 1),
        { id: maxId + 1, role: event.role, text: event.text, final: false },
      ]
    }
    const nextText =
      event.final || event.text.length >= open.text.length ? event.text : open.text
    const updated: TranscriptBubble = {
      ...open,
      text: nextText,
      final: event.final,
    }
    return [...prev.slice(0, openIdx), updated, ...prev.slice(openIdx + 1)]
  }

  let maxId = 0
  for (const bubble of prev) {
    if (bubble.id > maxId) maxId = bubble.id
  }
  return [
    ...prev,
    {
      id: maxId + 1,
      role: event.role,
      text: event.text,
      final: event.final,
    },
  ]
}

/**
 * Match a live `cc.transcript` event to the panel's active call.
 *
 * Internal WebRTC rings use a synthetic `call_id` (`internal:{offer_id}`) while
 * ASR events carry the real customer leg; accept either id (same idea as
 * {@link hangupMatches} for hangup).
 */
export function transcriptCallIdMatches(opts: {
  eventCallId?: string | null
  callId?: string | null
  sourceCallId?: string | null
}): boolean {
  const cid = opts.eventCallId
  if (!cid) return false
  return cid === opts.callId || (!!opts.sourceCallId && cid === opts.sourceCallId)
}

export function CallTranscriptPanel({
  callId,
  live,
  ringing = false,
  hideBot = false,
  fallbackRecordId,
  sourceCallId,
  flushTop = false,
  onShownChange,
  onContentChange,
}: {
  callId: string
  live: boolean
  /** Ringing screen-pop: show bot segment, hide the whole area if no bot. */
  ringing?: boolean
  /** Internal consult / conference invite — do not fetch bot transcript. */
  hideBot?: boolean
  /** When live captions were cleared (e.g. remount after browsing history), show persisted lines. */
  fallbackRecordId?: string | null
  /** Real customer leg id when `callId` is a synthetic internal offer id. */
  sourceCallId?: string | null
  /** Drop the top rule when call facts above are folded away. */
  flushTop?: boolean
  /** Reports whether this panel is actually on screen (ringing hides it when there is no bot). */
  onShownChange?: (shown: boolean) => void
  /** Reports whether any conversation line exists; `null` while still loading. */
  onContentChange?: (hasContent: boolean | null) => void
}) {
  const { socket } = useSocketStore()
  const { locale } = useLocaleStore()
  const { data: settings } = useSystemSettings()
  const asrEnabled = settings?.bridge_asr_enabled ?? false
  const botQuery = useBotTranscript(hideBot ? null : callId)
  const bot = botQuery.data
  const showBot = !hideBot && (botQuery.isPending || botQuery.isError || Boolean(bot?.available))
  const conversationScrollRef = useRef<HTMLDivElement>(null)
  const [captions, setCaptions] = useState<TranscriptBubble[]>([])
  const nextIdRef = useRef(0)
  const hydratedCallIdRef = useRef<string | null>(null)
  // Always load persisted finals when we have a record id — after a page
  // refresh live captions are empty otherwise (socket history is gone).
  const historyQuery = useCallTranscript(fallbackRecordId ?? null)
  const historySegments = historyQuery.data?.segments

  // Media-leg rebuilds (transfer handover, reconnect) can swap `callId`
  // mid-conversation; only a genuinely new conversation clears live captions.
  const conversationKey = sourceCallId ?? callId
  useEffect(() => {
    setCaptions([])
    hydratedCallIdRef.current = null
    nextIdRef.current = 0
  }, [conversationKey])

  // Seed in-memory captions from DB so refresh mid-call keeps prior lines.
  useEffect(() => {
    if (!live || !callId) return
    if (hydratedCallIdRef.current === callId) return
    if (!historySegments?.length) return
    setCaptions((prev) => {
      hydratedCallIdRef.current = callId
      if (prev.length > 0) return prev
      return historySegments.map((s) => ({
        id: nextIdRef.current++,
        role: s.role,
        text: s.text,
        final: true,
      }))
    })
  }, [live, callId, historySegments])

  // Hangup often arrives before open partial captions are marked final.
  useEffect(() => {
    if (live) return
    setCaptions((prev) => {
      if (!prev.some((b) => b.final === false)) return prev
      return prev.map((b) => (b.final === false ? { ...b, final: true } : b))
    })
  }, [live])

  useEffect(() => {
    if (!socket || !callId || !live) return

    const onTranscript = (data: TranscriptEvent) => {
      if (
        !transcriptCallIdMatches({
          eventCallId: data.call_id,
          callId,
          sourceCallId,
        })
      ) {
        return
      }
      const text = (data.text ?? '').trim()
      if (!text) return
      setCaptions((prev) =>
        applyTranscriptEvent(prev, { role: data.role, text, final: data.final }),
      )
    }

    socket.on('cc.transcript', onTranscript)
    return () => {
      socket.off('cc.transcript', onTranscript)
    }
  }, [socket, callId, sourceCallId, live])

  const showHistoryFallback =
    !live && captions.length === 0 && (historySegments?.length ?? 0) > 0
  // While the bot query is still pending, keep call facts open so a normal
  // ring does not collapse and then snap back open.
  const transcriptShown = ringing ? showBot && !botQuery.isPending : true

  useEffect(() => {
    onShownChange?.(transcriptShown)
  }, [onShownChange, transcriptShown])

  useEffect(() => {
    return () => onShownChange?.(false)
  }, [onShownChange])

  const hasContent =
    captions.length > 0 || showHistoryFallback || (showBot && (bot?.messages.length ?? 0) > 0)
      ? true
      : (showBot && botQuery.isPending) || historyQuery.isLoading
        ? null
        : false
  useEffect(() => {
    onContentChange?.(hasContent)
  }, [onContentChange, hasContent])

  useEffect(() => {
    if (!live && !ringing) return
    const el = conversationScrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [live, ringing, captions, bot?.messages])

  if (ringing && !showBot) return null

  const agentTitle = showHistoryFallback ? '对话记录' : '实时对话'
  const agentNote = !asrEnabled
    ? '暂未开启转写'
    : captions.length > 0 || showHistoryFallback
      ? null
      : live
        ? historyQuery.isLoading
          ? '对话记录加载中…'
          : '正在聆听通话，识别到对话后实时显示…'
        : historyQuery.isLoading
          ? '对话记录加载中…'
          : '暂无对话记录'
  const agentItems: TranscriptBubble[] = captions.length > 0
    ? captions
    : showHistoryFallback
      ? (historySegments ?? []).map((s) => ({
          id: s.id,
          role: s.role,
          text: s.text,
        }))
      : []

  return (
    <ConversationColumn
      flushTop={flushTop}
      scrollRef={conversationScrollRef}
      bot={
        showBot ? (
          <BotSegmentView
            locale={locale}
            queryPending={botQuery.isPending || botQuery.isFetching}
            queryError={botQuery.isError}
            data={bot}
            onRetry={() => {
              void botQuery.refetch()
            }}
          />
        ) : null
      }
      divider={
        showBot &&
        !botQuery.isPending &&
        !botQuery.isError &&
        bot?.available &&
        (bot.entered_human || ringing)
          ? bot
          : undefined
      }
      locale={locale}
      agentTitle={ringing ? undefined : agentTitle}
      agentItems={ringing ? [] : agentItems}
      agentNote={ringing ? undefined : agentNote}
    />
  )
}

/**
 * Persisted transcript for a finished/historical call. Hidden when the call has
 * no stored lines (e.g. it never reached a human agent).
 */
export function CallTranscriptHistory({
  recordId,
  flushTop = false,
  onContentChange,
}: {
  recordId: string
  /** Drop the top rule when call facts above are folded away. */
  flushTop?: boolean
  /** Reports whether any conversation line exists; `null` while still loading. */
  onContentChange?: (hasContent: boolean | null) => void
}) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useCallTranscript(recordId)
  const botQuery = useRecordBotTranscript(recordId)
  const bot = botQuery.data
  const showBot = botQuery.isPending || botQuery.isError || Boolean(bot?.available)
  const segments = data?.segments ?? []
  const hasContent =
    segments.length > 0 || (bot?.messages.length ?? 0) > 0
      ? true
      : isLoading || botQuery.isPending
        ? null
        : false
  useEffect(() => {
    onContentChange?.(hasContent)
  }, [onContentChange, hasContent])
  const agentNote = isLoading
    ? '对话记录加载中…'
    : segments.length === 0
      ? '暂无对话记录'
      : null
  return (
    <ConversationColumn
      flushTop={flushTop}
      bot={
        showBot ? (
          <BotSegmentView
            locale={locale}
            queryPending={botQuery.isPending || botQuery.isFetching}
            queryError={botQuery.isError}
            data={bot}
            onRetry={() => {
              void botQuery.refetch()
            }}
          />
        ) : null
      }
      divider={showBot && bot?.entered_human ? bot : undefined}
      locale={locale}
      agentTitle="对话记录"
      agentItems={segments.map((s) => ({ id: s.id, role: s.role, text: s.text }))}
      agentNote={agentNote}
    />
  )
}

function ConversationColumn({
  flushTop = false,
  scrollRef,
  bot,
  divider,
  locale,
  agentTitle,
  agentItems,
  agentNote,
}: {
  flushTop?: boolean
  scrollRef?: RefObject<HTMLDivElement | null>
  bot: ReactNode
  divider?: Pick<BotTranscriptResponse, 'handoff_at'> | undefined
  locale: Locale
  agentTitle?: string
  agentItems: TranscriptBubble[]
  agentNote?: string | null
}) {
  return (
    <section
      className={
        flushTop
          ? 'flex min-h-0 flex-1 flex-col pt-3'
          : 'mt-4 flex min-h-0 flex-1 flex-col border-t border-border pt-4'
      }
    >
      <div
        ref={scrollRef}
        className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto"
      >
        <div className="mt-auto flex flex-col gap-2">
          {bot}
          {divider && <HandoffLine locale={locale} handoffAt={divider.handoff_at} />}
          {agentTitle && (
            <h4 className="shrink-0 text-xs font-semibold text-foreground/70">{agentTitle}</h4>
          )}
          {agentItems.length > 0 && <TranscriptBubbles items={agentItems} embedded />}
          {agentNote && (
            <p className="flex min-h-16 items-center justify-center text-center text-xs text-muted-foreground">
              {agentNote}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

function BotSegmentView({
  locale,
  queryPending,
  queryError,
  data,
  onRetry,
}: {
  locale: Locale
  queryPending: boolean
  queryError: boolean
  data?: BotTranscriptResponse
  onRetry: () => void
}) {
  const failed = queryError || data?.status === 'error'
  const empty = !failed && !queryPending && (data?.status === 'empty' || (data?.messages.length ?? 0) === 0)
  const name = data?.agent_name
  return (
    <section className="flex flex-col gap-2">
      <div className="flex shrink-0 items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold text-foreground/70">
          {t('ws.call.botConversation', locale)}
        </h4>
        {name && !queryPending && !failed && (
          <span className="text-xs text-muted-foreground">
            {t('ws.call.botHandledBy', locale, { name })}
          </span>
        )}
      </div>
      {queryPending && (
        <SegmentNote>{t('ws.call.botLoading', locale)}</SegmentNote>
      )}
      {!queryPending && failed && (
        <SegmentNote>
          {t('ws.call.botLoadFailed', locale)}
          <button
            type="button"
            onClick={onRetry}
            disabled={queryPending}
            className="ml-2 text-xs text-primary disabled:opacity-50"
          >
            {t('ws.call.retry', locale)}
          </button>
        </SegmentNote>
      )}
      {!queryPending && !failed && empty && (
        <SegmentNote>{t('ws.call.botEmpty', locale)}</SegmentNote>
      )}
      {!queryPending && !failed && data && data.messages.length > 0 && (
        <TranscriptBubbles
          embedded
          items={data.messages.map((m, index) => ({
            id: index + 1,
            role: m.role,
            text: m.text,
            interrupted: m.interrupted,
          }))}
        />
      )}
    </section>
  )
}

function SegmentNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex min-h-16 items-center justify-center text-center text-xs text-muted-foreground">
      {children}
    </p>
  )
}

function HandoffLine({ locale, handoffAt }: { locale: Locale; handoffAt: string | null }) {
  const time = formatHandoffTime(handoffAt)
  const label = time
    ? t('ws.call.transferredToAgentAt', locale, { time })
    : t('ws.call.transferredToAgent', locale)
  return (
    <div className="my-2 flex shrink-0 items-center gap-3">
      <div className="h-px flex-1 bg-border" />
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

export function formatHandoffTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleTimeString(undefined, {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
