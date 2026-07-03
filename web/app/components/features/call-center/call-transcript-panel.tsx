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

export function CallTranscriptPanel({ callId, live }: { callId: string; live: boolean }) {
  const { socket } = useSocketStore()
  const { data: settings } = useSystemSettings()
  const asrEnabled = settings?.bridge_asr_enabled ?? false
  const [captions, setCaptions] = useState<TranscriptBubble[]>([])
  const nextIdRef = useRef(0)

  // A new call starts a fresh transcript.
  useEffect(() => {
    setCaptions([])
  }, [callId])

  useEffect(() => {
    if (!socket || !callId) return

    const onTranscript = (data: TranscriptEvent) => {
      if (data.call_id !== callId) return
      const text = (data.text ?? '').trim()
      if (!text) return
      setCaptions((prev) => {
        const last = prev[prev.length - 1]
        // A streaming caption (same role, not yet final) gets replaced in place;
        // anything else opens a new bubble.
        if (last && last.role === data.role && last.final === false) {
          const updated: TranscriptBubble = { ...last, text, final: data.final }
          return [...prev.slice(0, -1), updated]
        }
        const created: TranscriptBubble = {
          id: nextIdRef.current++,
          role: data.role,
          text,
          final: data.final,
        }
        return [...prev, created]
      })
    }

    socket.on('cc.transcript', onTranscript)
    return () => {
      socket.off('cc.transcript', onTranscript)
    }
  }, [socket, callId])

  return (
    <section className="mt-4 border-t border-border pt-4">
      <h4 className="mb-2 text-xs font-semibold text-foreground/70">实时对话</h4>
      {!asrEnabled ? (
        <p className="py-6 text-center text-xs text-muted-foreground">暂未开启转写</p>
      ) : captions.length === 0 ? (
        <p className="py-6 text-center text-xs text-muted-foreground">
          {live ? '正在聆听通话，识别到对话后实时显示…' : '坐席接入后，这里实时显示与用户的对话'}
        </p>
      ) : (
        <TranscriptBubbles items={captions} autoScroll />
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
  if (isLoading || segments.length === 0) return null
  return (
    <section className="mt-4 border-t border-border pt-4">
      <h4 className="mb-2 text-xs font-semibold text-foreground/70">对话记录</h4>
      <TranscriptBubbles
        items={segments.map((s) => ({ id: s.id, role: s.role, text: s.text }))}
      />
    </section>
  )
}
