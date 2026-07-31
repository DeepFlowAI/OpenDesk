'use client'

import { useEffect, useRef, useState } from 'react'

import { useSocketStore } from '@/context/socket-store'
import { useCallTranscript } from '@/service/use-call-center'
import { useSystemSettings } from '@/service/use-system-settings'
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
 * flicker; a matching final replaces the open bubble in place.
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
  fallbackRecordId,
  sourceCallId,
}: {
  callId: string
  live: boolean
  /** When live captions were cleared (e.g. remount after browsing history), show persisted lines. */
  fallbackRecordId?: number | null
  /** Real customer leg id when `callId` is a synthetic internal offer id. */
  sourceCallId?: string | null
}) {
  const { socket } = useSocketStore()
  const { data: settings } = useSystemSettings()
  const asrEnabled = settings?.bridge_asr_enabled ?? false
  const [captions, setCaptions] = useState<TranscriptBubble[]>([])
  const nextIdRef = useRef(0)
  const hydratedCallIdRef = useRef<string | null>(null)
  // Always load persisted finals when we have a record id — after a page
  // refresh live captions are empty otherwise (socket history is gone).
  const historyQuery = useCallTranscript(fallbackRecordId ?? null)
  const historySegments = historyQuery.data?.segments

  // A new call starts a fresh transcript.
  useEffect(() => {
    setCaptions([])
    hydratedCallIdRef.current = null
    nextIdRef.current = 0
  }, [callId])

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

  return (
    <section className="mt-4 flex min-h-0 flex-1 flex-col border-t border-border pt-4">
      <h4 className="mb-2 shrink-0 text-xs font-semibold text-foreground/70">
        {showHistoryFallback ? '对话记录' : '实时对话'}
      </h4>
      {!asrEnabled ? (
        <p className="py-6 text-center text-xs text-muted-foreground">暂未开启转写</p>
      ) : captions.length > 0 ? (
        <TranscriptBubbles items={captions} autoScroll={live} fill />
      ) : showHistoryFallback ? (
        <TranscriptBubbles
          fill
          items={(historySegments ?? []).map((s) => ({
            id: s.id,
            role: s.role,
            text: s.text,
          }))}
        />
      ) : (
        <p className="flex min-h-0 flex-1 items-center justify-center py-6 text-center text-xs text-muted-foreground">
          {live
            ? historyQuery.isLoading
              ? '对话记录加载中…'
              : '正在聆听通话，识别到对话后实时显示…'
            : historyQuery.isLoading
              ? '对话记录加载中…'
              : '暂无对话记录'}
        </p>
      )}
    </section>
  )
}

/**
 * Persisted transcript for a finished/historical call. Hidden when the call has
 * no stored lines (e.g. it never reached a human agent).
 */
export function CallTranscriptHistory({ recordId }: { recordId: number }) {
  const { data, isLoading } = useCallTranscript(recordId)
  const segments = data?.segments ?? []
  return (
    <section className="mt-4 flex min-h-0 flex-1 flex-col border-t border-border pt-4">
      <h4 className="mb-2 shrink-0 text-xs font-semibold text-foreground/70">对话记录</h4>
      {isLoading ? (
        <p className="flex min-h-0 flex-1 items-end justify-center py-6 text-center text-xs text-muted-foreground">
          对话记录加载中…
        </p>
      ) : segments.length === 0 ? (
        <p className="flex min-h-0 flex-1 items-end justify-center py-6 text-center text-xs text-muted-foreground">
          暂无对话记录
        </p>
      ) : (
        <TranscriptBubbles
          fill
          items={segments.map((s) => ({ id: s.id, role: s.role, text: s.text }))}
        />
      )}
    </section>
  )
}
