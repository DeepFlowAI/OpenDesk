'use client'
import { useEffect, useState } from 'react'

export type MicState = 'checking' | 'granted' | 'denied' | 'prompt' | 'error'

/**
 * Microphone permission + media stream hook.
 *
 * Behavior:
 *  - On mount, queries permissions.query({ name: 'microphone' }).
 *  - If 'granted' → immediately `getUserMedia({ audio: true })`.
 *  - If 'prompt' → waits for `request()` to be called.
 *  - If 'denied' → exposes state for UI to render the "go to settings" banner.
 */
type UseMicrophoneOptions = {
  autoRequestOnGranted?: boolean
}

export function useMicrophone(options: UseMicrophoneOptions = {}) {
  const { autoRequestOnGranted = true } = options
  const [state, setState] = useState<MicState>('checking')
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
        if (!cancelled) setState('error')
        return
      }
      try {
        const status = await (
          navigator.permissions
            ?.query({ name: 'microphone' as PermissionName })
            .catch(() => null)
        )
        if (cancelled) return
        if (status?.state === 'granted' && autoRequestOnGranted) {
          await request()
        } else if (status?.state === 'granted') {
          setState('granted')
        } else if (status?.state === 'denied') {
          setState('denied')
        } else {
          setState('prompt')
        }
      } catch {
        if (!cancelled) setState('prompt')
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const request = async (): Promise<boolean> => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true })
      setStream(s)
      setState('granted')
      return true
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      setState('denied')
      return false
    }
  }

  const stop = () => {
    stream?.getTracks().forEach((t) => t.stop())
    setStream(null)
  }

  return { state, stream, error, request, stop }
}
