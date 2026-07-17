'use client'
/**
 * Supervisor WebRTC media-leg lifecycle for call intervention.
 *
 * A supervisor can listen with no media leg (server-side one-way monitor).
 * To speak — whisper / barge / takeover — the supervisor needs their own
 * WebRTC leg mixed into the room. This hook runs that handshake:
 *
 *   ensureLeg(callId):
 *     getUserMedia(mic) → RTCPeerConnection → createOffer
 *     → POST /reports/call-monitor/live/calls/{callId}/webrtc/offer { sdp }
 *     → server: webrtc.offer + call.answer + record supervisor leg id
 *     → response: { supervisor_call_id, sdp }
 *     → setRemoteDescription(answer)
 *
 *   release(): close PC + release mic + clear remote audio
 *
 *   applyRemoteIce(candidate): from Socket.IO `cc.supervisor.ice` event.
 *
 * Mirrors the agent `useWebRTCLeg` trickle-ICE pattern: the offer is sent
 * immediately (no gathering wait, which hangs on restrictive networks), the
 * browser's candidates are trickled to the kernel, and the kernel's candidates
 * arrive over a socket.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import {
  postSupervisorIce,
  postSupervisorWebRTCOffer,
} from '@/service/use-call-intervention'

type LegState = 'idle' | 'connecting' | 'ready' | 'failed' | 'closed'

const DEFAULT_ICE: RTCIceServer[] = [{ urls: 'stun:stun.l.google.com:19302' }]

function log(...args: unknown[]) {
  console.log('[supervisor-leg]', ...args)
}

export function useSupervisorLeg() {
  const [state, setState] = useState<LegState>('idle')
  const [muted, setMuted] = useState(false)
  const [supervisorCallId, setSupervisorCallId] = useState<string | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null)
  const isClosingRef = useRef(false)
  const pendingLocalCandidates = useRef<RTCIceCandidate[]>([])
  // The target call id candidates are POSTed against — the backend resolves the
  // supervisor's own leg from the monitor holder. Set once the offer returns.
  const supervisorCallIdRef = useRef<string | null>(null)
  const targetCallIdRef = useRef<string | null>(null)

  const ensureRemoteAudio = useCallback(() => {
    if (remoteAudioRef.current) return remoteAudioRef.current
    const el = document.createElement('audio')
    el.autoplay = true
    el.style.display = 'none'
    document.body.appendChild(el)
    remoteAudioRef.current = el
    return el
  }, [])

  const teardown = useCallback(() => {
    isClosingRef.current = true
    pcRef.current?.close()
    pcRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (remoteAudioRef.current) {
      remoteAudioRef.current.srcObject = null
      remoteAudioRef.current.remove()
      remoteAudioRef.current = null
    }
    pendingLocalCandidates.current = []
    supervisorCallIdRef.current = null
    targetCallIdRef.current = null
    setMuted(false)
  }, [])

  /** Toggle the supervisor's own microphone (local track enable). */
  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev
      streamRef.current?.getAudioTracks().forEach((t) => {
        t.enabled = !next
      })
      return next
    })
  }, [])

  /**
   * Ensure the supervisor's media leg is up for `callId`. Idempotent: returns
   * the existing leg id when already connected. Returns the leg id, or null on
   * failure.
   */
  const ensureLeg = useCallback(
    async (callId: string): Promise<string | null> => {
      if (state === 'ready' && supervisorCallId) return supervisorCallId
      if (state === 'connecting') return null
      setState('connecting')
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        streamRef.current = stream

        const pc = new RTCPeerConnection({ iceServers: DEFAULT_ICE })
        pcRef.current = pc
        isClosingRef.current = false
        targetCallIdRef.current = callId
        stream.getTracks().forEach((t) => pc.addTrack(t, stream))
        pc.ontrack = (ev) => {
          const audio = ensureRemoteAudio()
          audio.srcObject = ev.streams[0]
        }
        pc.onconnectionstatechange = () => {
          if (pc.connectionState === 'failed' && !isClosingRef.current) setState('failed')
        }
        pc.onicecandidate = async (ev) => {
          if (!ev.candidate) return
          // Buffer until the offer response confirms the supervisor leg exists;
          // candidates are POSTed against the target call id.
          if (!supervisorCallIdRef.current) {
            pendingLocalCandidates.current.push(ev.candidate)
            return
          }
          try {
            await postSupervisorIce(callId, {
              candidate: ev.candidate.candidate,
              sdp_mid: ev.candidate.sdpMid,
              sdp_m_line_index: ev.candidate.sdpMLineIndex,
            })
          } catch (e) {
            console.warn('[supervisor-leg] ice upstream failed', e)
          }
        }

        const offer = await pc.createOffer({ offerToReceiveAudio: true })
        await pc.setLocalDescription(offer)

        // Send the offer immediately — do NOT wait for ICE gathering to
        // complete (that hangs on restrictive networks). Candidates trickle up.
        const result = await postSupervisorWebRTCOffer(callId, offer.sdp ?? '')
        supervisorCallIdRef.current = result.supervisor_call_id

        for (const c of pendingLocalCandidates.current) {
          postSupervisorIce(callId, {
            candidate: c.candidate,
            sdp_mid: c.sdpMid,
            sdp_m_line_index: c.sdpMLineIndex,
          }).catch(() => {})
        }
        pendingLocalCandidates.current = []

        await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp || '' })
        setSupervisorCallId(result.supervisor_call_id)
        setState('ready')
        log('ready call_id=', result.supervisor_call_id)
        return result.supervisor_call_id
      } catch (e) {
        console.error('[supervisor-leg] ensureLeg FAILED:', e)
        setState('failed')
        teardown()
        return null
      }
    },
    [state, supervisorCallId, ensureRemoteAudio, teardown],
  )

  const applyRemoteIce = useCallback(async (candidate: RTCIceCandidateInit) => {
    const pc = pcRef.current
    if (!pc) return
    try {
      await pc.addIceCandidate(candidate)
    } catch (e) {
      console.warn('[supervisor-leg] applyRemoteIce failed', e)
    }
  }, [])

  const release = useCallback(() => {
    teardown()
    setSupervisorCallId(null)
    setState('closed')
  }, [teardown])

  useEffect(() => () => release(), [release])

  return { state, muted, supervisorCallId, ensureLeg, release, applyRemoteIce, toggleMute }
}
