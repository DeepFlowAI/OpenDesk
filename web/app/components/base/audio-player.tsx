'use client'
/**
 * Reusable local preview control (play / stop).
 *
 * - `mode="audio"`: plays a remote audio URL via an <audio> element.
 * - `mode="tts"`: previews text with the browser SpeechSynthesis API
 *   (no backend TTS preview endpoint exists yet, so preview stays in-browser).
 *
 * Playback is local only — it never places a real call. A shared token lets
 * callers ensure only one player is active at a time: when the active token
 * changes, every other instance stops.
 */
import { useEffect, useRef, useState } from 'react'
import { IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react'

type AudioPlayerProps = {
  mode: 'tts' | 'audio'
  /** Remote audio url when mode === 'audio'. */
  url?: string | null
  /** Text to speak when mode === 'tts'. */
  text?: string | null
  /** Locale for speech synthesis (e.g. 'zh' | 'en'). */
  lang?: string
  playLabel: string
  stopLabel: string
  disabled?: boolean
  /** Shared active id; when it changes to another id, this instance stops. */
  activeToken?: string | null
  /** Unique id for this player instance. */
  token: string
  onActivate?: (token: string) => void
  onDeactivate?: () => void
  onError?: (message: string) => void
}

export function AudioPlayer({
  mode,
  url,
  text,
  lang = 'zh',
  playLabel,
  stopLabel,
  disabled,
  activeToken,
  token,
  onActivate,
  onDeactivate,
  onError,
}: AudioPlayerProps) {
  const [playing, setPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const stoppingRef = useRef(false)

  const stop = () => {
    stoppingRef.current = true
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    setPlaying(false)
  }

  // Stop when another player becomes active or when unmounting.
  useEffect(() => {
    if (activeToken && activeToken !== token && playing) stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeToken])

  useEffect(() => () => stop(), [])

  const play = () => {
    stoppingRef.current = false
    onActivate?.(token)
    setPlaying(true)

    if (mode === 'audio') {
      if (!url) {
        setPlaying(false)
        onError?.('missing-url')
        return
      }
      const el = new Audio(url)
      audioRef.current = el
      el.onended = () => {
        setPlaying(false)
        onDeactivate?.()
      }
      el.onerror = () => {
        setPlaying(false)
        onDeactivate?.()
        onError?.('load-failed')
      }
      el.play().catch(() => {
        setPlaying(false)
        onDeactivate?.()
        onError?.('load-failed')
      })
      return
    }

    // TTS: browser speech synthesis preview.
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      setPlaying(false)
      onError?.('unsupported')
      return
    }
    const trimmed = (text ?? '').trim()
    if (!trimmed) {
      setPlaying(false)
      onError?.('empty')
      return
    }
    const utter = new SpeechSynthesisUtterance(trimmed)
    utter.lang = lang === 'en' ? 'en-US' : 'zh-CN'
    utter.onend = () => {
      setPlaying(false)
      onDeactivate?.()
    }
    utter.onerror = (event) => {
      const intentional = stoppingRef.current
      stoppingRef.current = false
      setPlaying(false)
      onDeactivate?.()
      // Stop/close while speaking fires interrupted/canceled — not a real failure.
      const err = (event as SpeechSynthesisErrorEvent).error
      if (intentional || err === 'interrupted' || err === 'canceled') return
      onError?.('load-failed')
    }
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utter)
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => (playing ? stop() : play())}
      className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-50"
    >
      {playing ? (
        <IconPlayerStop className="size-4" />
      ) : (
        <IconPlayerPlay className="size-4" />
      )}
      {playing ? stopLabel : playLabel}
    </button>
  )
}
