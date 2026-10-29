'use client'
/**
 * One-shot bell played on the agent's own speaker when the Web phone
 * auto-answers a call. It is a plain HTMLAudioElement, so it never enters
 * the WebRTC uplink and the customer / recording cannot hear it.
 */
import { useCallback, useEffect, useMemo, useRef } from 'react'

const AUTO_ANSWER_CHIME_SRC = '/audio/auto-answer-bell.mp3'

export function useAutoAnswerChime() {
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const stop = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.pause()
    audio.currentTime = 0
  }, [])

  const play = useCallback(() => {
    if (typeof window === 'undefined') return
    if (!audioRef.current) {
      audioRef.current = new Audio(AUTO_ANSWER_CHIME_SRC)
      audioRef.current.preload = 'auto'
    }
    const audio = audioRef.current
    audio.pause()
    audio.currentTime = 0
    audio.play().catch(() => {
      // Autoplay block / load / decode failure must not affect the answer.
    })
  }, [])

  useEffect(() => () => stop(), [stop])

  return useMemo(() => ({ play, stop }), [play, stop])
}
