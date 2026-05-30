'use client'
/**
 * Synthesized ringtone — no audio asset to ship.
 *
 * Generates a classic "ring–ring … silence" cadence with the WebAudio API:
 *   2 seconds of dual-tone (440 Hz + 480 Hz, standard PSTN ringback flavor)
 *   followed by 4 seconds of silence, looping.
 *
 * Browser autoplay policies require a prior user gesture, but by the time
 * we'd play this the agent has already interacted with the workspace
 * (clicked "就绪" / accepted mic permission), so playback works.
 */
import { useCallback, useEffect, useRef } from 'react'

export function useRingtone() {
  const ctxRef = useRef<AudioContext | null>(null)
  const sourcesRef = useRef<OscillatorNode[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const playingRef = useRef(false)

  const ensureCtx = (): AudioContext | null => {
    if (typeof window === 'undefined') return null
    if (!ctxRef.current) {
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      if (!AC) return null
      ctxRef.current = new AC()
    }
    return ctxRef.current
  }

  const stop = useCallback(() => {
    playingRef.current = false
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    for (const osc of sourcesRef.current) {
      try { osc.stop() } catch { /* already stopped */ }
      try { osc.disconnect() } catch { /* noop */ }
    }
    sourcesRef.current = []
  }, [])

  const start = useCallback(() => {
    const ctx = ensureCtx()
    if (!ctx) return
    if (playingRef.current) return
    playingRef.current = true
    // If the context is suspended by autoplay policy, resume on this gesture-
    // adjacent invocation (the call.incoming arrives after the agent already
    // clicked into the workspace, so this typically succeeds).
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {})
    }

    const ringOnce = () => {
      if (!playingRef.current) return
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0.001, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.05)
      gain.gain.setValueAtTime(0.15, ctx.currentTime + 1.95)
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 2.0)
      gain.connect(ctx.destination)

      const a = ctx.createOscillator()
      a.frequency.value = 440
      a.connect(gain)
      const b = ctx.createOscillator()
      b.frequency.value = 480
      b.connect(gain)
      a.start()
      b.start()
      a.stop(ctx.currentTime + 2.0)
      b.stop(ctx.currentTime + 2.0)
      sourcesRef.current = [a, b]

      timerRef.current = setTimeout(ringOnce, 6_000) // 2s on + 4s off
    }
    ringOnce()
  }, [])

  useEffect(() => () => stop(), [stop])

  return { start, stop }
}
