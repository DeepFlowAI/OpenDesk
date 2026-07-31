'use client'
/**
 * Ring-on-demand WebRTC leg lifecycle for an agent.
 *
 * The agent is "ready" without holding a media leg. When the orchestrator
 * pushes a call offer, we run getUserMedia + RTCPeerConnection here:
 *
 *   acceptOffer(offerId):
 *     getUserMedia(mic) → RTCPeerConnection → createOffer
 *     → POST /current-call/accept { offer_id, sdp }
 *     → server-side: webrtc.offer + call.answer + resolve pending offer
 *     → response: { call_id, sdp }
 *     → setRemoteDescription(answer)
 *     → onicecandidate → POST /webrtc/ice
 *
 *   goOffline(): close PC + release mic + clear remote audio
 *
 *   applyRemoteIce(candidate): from Socket.IO `cc.webrtc.ice` event.
 *
 * Every step writes `[webrtc-leg] ...` to console for DevTools diagnostics.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { HTTPError } from 'ky'

import {
  acceptCurrentCall,
  dialWebRTCOffer,
  postWebRTCIce,
  reconnectCurrentCallMedia,
} from '@/service/use-call-center'
import { mapOutboundFailure } from '@/app/components/features/call-center/outbound-failure-message'

type LegState = 'idle' | 'connecting' | 'ready' | 'failed' | 'closed'

const DEFAULT_ICE: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
]

function log(...args: unknown[]) {
  console.log('[webrtc-leg]', ...args)
}

/**
 * Translate a raw exception from the outbound-WebRTC handshake into a short
 * Chinese message safe to show in a toast. Never include URLs, HTTP status
 * codes, or stack traces — those are debug noise users can't act on.
 */
async function friendlyOriginateError(e: unknown): Promise<string> {
  if (e instanceof HTTPError) {
    try {
      const body = (await e.response.clone().json()) as {
        code?: string
        message?: string
        details?: { reason?: string | null; sip_status?: number | null }
      }
      if (
        e.response.status === 410 ||
        body?.code === 'OUTBOUND_CALL_ENDED'
      ) {
        const failure = mapOutboundFailure({
          reason: body?.details?.reason,
          sip_status: body?.details?.sip_status,
        })
        if (failure.message) return failure.message
        return '外呼已结束'
      }
      if (typeof body?.message === 'string' && body.message.trim()) {
        // Backend ValidationError / NotFoundError — show server message when
        // it is already Chinese; otherwise fall through to generic text.
        if (/[\u4e00-\u9fff]/.test(body.message)) return body.message.trim()
      }
      if (e.response.status === 404) return '外呼已结束或找不到该通话'
    } catch {
      // fall through
    }
  }
  if (e instanceof DOMException) {
    if (e.name === 'NotAllowedError') return '麦克风未授权，请在浏览器允许后重试'
    if (e.name === 'NotFoundError') return '未检测到可用麦克风'
    return '浏览器音频设备异常'
  }
  const msg = e instanceof Error ? e.message : ''
  if (/timeout/i.test(msg)) return '语音通道建立超时，请重试'
  if (/network|fetch/i.test(msg)) return '网络异常，无法建立语音通道'
  return '外呼失败，请稍后重试'
}

export function useWebRTCLeg() {
  const [state, setState] = useState<LegState>('idle')
  const [callId, setCallId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null)
  const pendingLocalCandidates = useRef<RTCIceCandidate[]>([])
  const callIdRef = useRef<string | null>(null)
  const isClosingRef = useRef(false)

  const ensureRemoteAudio = useCallback(() => {
    if (remoteAudioRef.current) return remoteAudioRef.current
    const el = document.createElement('audio')
    el.autoplay = true
    el.style.display = 'none'
    document.body.appendChild(el)
    remoteAudioRef.current = el
    return el
  }, [])

  const teardownPc = useCallback(() => {
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
    callIdRef.current = null
  }, [])

  /**
   * Run the full WebRTC setup against an inbound offer. Returns true on
   * success, false on failure (state is set accordingly).
   */
  const acceptOffer = useCallback(async (offerId: string): Promise<boolean> => {
    if (state === 'ready' || state === 'connecting') {
      log('acceptOffer: already', state, '— ignoring')
      return state === 'ready'
    }
    setState('connecting')
    setError(null)
    setCallId(null)
    log('acceptOffer: offer_id=', offerId)
    try {
      log('step 1: getUserMedia(audio)')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      log('step 1 ✓')

      log('step 2: new RTCPeerConnection')
      const pc = new RTCPeerConnection({ iceServers: DEFAULT_ICE })
      pcRef.current = pc
      isClosingRef.current = false

      stream.getTracks().forEach((t) => pc.addTrack(t, stream))

      pc.ontrack = (ev) => {
        log('ontrack')
        const audio = ensureRemoteAudio()
        audio.srcObject = ev.streams[0]
      }
      pc.onconnectionstatechange = () => {
        log('connectionState →', pc.connectionState)
        if (pc.connectionState === 'failed' && !isClosingRef.current) {
          setError('ICE 连接失败（UDP 16384-32767 可能不通）')
          setState('failed')
        }
      }
      pc.oniceconnectionstatechange = () => {
        log('iceConnectionState →', pc.iceConnectionState)
      }
      pc.onicecandidate = async (ev) => {
        if (!ev.candidate) {
          log('onicecandidate: gathering complete')
          return
        }
        const cid = callIdRef.current
        if (!cid) {
          pendingLocalCandidates.current.push(ev.candidate)
          return
        }
        try {
          await postWebRTCIce(cid, {
            candidate: ev.candidate.candidate,
            sdp_mid: ev.candidate.sdpMid,
            sdp_m_line_index: ev.candidate.sdpMLineIndex,
          })
        } catch (e) {
          console.warn('[webrtc-leg] ice upstream failed', e)
        }
      }

      log('step 3: createOffer + setLocalDescription')
      const offer = await pc.createOffer({ offerToReceiveAudio: true })
      await pc.setLocalDescription(offer)

      log('step 4: POST /current-call/accept')
      const result = await acceptCurrentCall({ offer_id: offerId, sdp: offer.sdp ?? '' })
      if (!result.ok || !result.call_id) {
        throw new Error(result.error || 'accept_failed')
      }
      log('step 4 ✓ call_id=', result.call_id)
      callIdRef.current = result.call_id
      setCallId(result.call_id)

      for (const c of pendingLocalCandidates.current) {
        postWebRTCIce(result.call_id, {
          candidate: c.candidate,
          sdp_mid: c.sdpMid,
          sdp_m_line_index: c.sdpMLineIndex,
        }).catch(() => {})
      }
      pendingLocalCandidates.current = []

      log('step 5: setRemoteDescription(answer)')
      await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp || '' })
      setState('ready')
      log('acceptOffer ✓ ready')
      return true
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e) || 'unknown error'
      console.error('[webrtc-leg] acceptOffer FAILED:', e)
      setError(msg)
      setState('failed')
      teardownPc()
      return false
    }
  }, [ensureRemoteAudio, state, teardownPc])

  /**
   * Run the same WebRTC setup but POST the SDP to /dial-webrtc/offer
   * instead of /current-call/accept. Used for agent-initiated outbound
   * calls — the outbound SIP leg is already in flight; this attaches
   * the agent's audio leg so the orchestrator can bridge them when the
   * carrier answers.
   *
   * Returns null on success, or a ready-to-toast Chinese error string.
   * Callers must use the returned string (not `error` state) — React state
   * updates are async and would race the dial UI cleanup.
   */
  const originateOffer = useCallback(async (outboundCallId: string): Promise<string | null> => {
    if (state === 'ready' || state === 'connecting') {
      log('originateOffer: already', state, '— ignoring')
      return state === 'ready' ? null : '语音通道正在连接，请稍候'
    }
    setState('connecting')
    setError(null)
    setCallId(null)
    log('originateOffer: outbound_call_id=', outboundCallId)
    try {
      log('step 1: getUserMedia(audio)')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      log('step 1 ✓')

      log('step 2: new RTCPeerConnection')
      const pc = new RTCPeerConnection({ iceServers: DEFAULT_ICE })
      pcRef.current = pc
      isClosingRef.current = false

      stream.getTracks().forEach((t) => pc.addTrack(t, stream))

      pc.ontrack = (ev) => {
        log('ontrack')
        const audio = ensureRemoteAudio()
        audio.srcObject = ev.streams[0]
      }
      pc.onconnectionstatechange = () => {
        log('connectionState →', pc.connectionState)
        if (pc.connectionState === 'failed' && !isClosingRef.current) {
          setError('ICE 连接失败（UDP 16384-32767 可能不通）')
          setState('failed')
        }
      }
      pc.oniceconnectionstatechange = () => {
        log('iceConnectionState →', pc.iceConnectionState)
      }
      pc.onicecandidate = async (ev) => {
        if (!ev.candidate) {
          log('onicecandidate: gathering complete')
          return
        }
        const cid = callIdRef.current
        if (!cid) {
          pendingLocalCandidates.current.push(ev.candidate)
          return
        }
        try {
          await postWebRTCIce(cid, {
            candidate: ev.candidate.candidate,
            sdp_mid: ev.candidate.sdpMid,
            sdp_m_line_index: ev.candidate.sdpMLineIndex,
          })
        } catch (e) {
          console.warn('[webrtc-leg] ice upstream failed', e)
        }
      }

      log('step 3: createOffer + setLocalDescription')
      const offer = await pc.createOffer({ offerToReceiveAudio: true })
      await pc.setLocalDescription(offer)

      log('step 4: POST /dial-webrtc/offer')
      const result = await dialWebRTCOffer({
        outbound_call_id: outboundCallId,
        sdp: offer.sdp ?? '',
      })
      log('step 4 ✓ webrtc_call_id=', result.webrtc_call_id)
      callIdRef.current = result.webrtc_call_id
      setCallId(result.webrtc_call_id)

      for (const c of pendingLocalCandidates.current) {
        postWebRTCIce(result.webrtc_call_id, {
          candidate: c.candidate,
          sdp_mid: c.sdpMid,
          sdp_m_line_index: c.sdpMLineIndex,
        }).catch(() => {})
      }
      pendingLocalCandidates.current = []

      log('step 5: setRemoteDescription(answer)')
      await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp || '' })
      setState('ready')
      log('originateOffer ✓ ready (waiting for SIP answered → bridge)')
      return null
    } catch (e: unknown) {
      console.error('[webrtc-leg] originateOffer FAILED:', e)
      // Carrier may reject before getUserMedia finishes; backend returns
      // 410 OUTBOUND_CALL_ENDED with reason/sip_status. Return the message
      // so the dial UI can toast even if cc.outbound_hangup was lost/raced.
      const friendlyMsg = await friendlyOriginateError(e)
      setError(friendlyMsg)
      setState('failed')
      teardownPc()
      return friendlyMsg
    }
  }, [ensureRemoteAudio, state, teardownPc])

  /**
   * Toggle the local microphone track (track.enabled=false), which takes
   * effect at once and needs no server round trip.
   *
   * Returns whether a local track was actually switched. False means this
   * agent is on a device without one — a SIP handset — and muting them can
   * only be done by the media kernel, so the caller must not treat the button
   * as already effective.
   */
  const setMuted = useCallback((muted: boolean): boolean => {
    const stream = streamRef.current
    if (!stream) return false
    const tracks = stream.getAudioTracks()
    tracks.forEach((track) => {
      track.enabled = !muted
    })
    log('setMuted', muted)
    return tracks.length > 0
  }, [])

  const applyRemoteIce = useCallback(async (candidate: RTCIceCandidateInit) => {
    const pc = pcRef.current
    if (!pc) return
    try {
      await pc.addIceCandidate(candidate)
    } catch (e) {
      console.warn('[webrtc-leg] applyRemoteIce failed', e)
    }
  }, [])

  const goOffline = useCallback(() => {
    log('goOffline')
    teardownPc()
    setCallId(null)
    setError(null)
    setState('closed')
  }, [teardownPc])

  /**
   * Rebuild a media leg for an already-active customer call (page refresh /
   * media_eof / consult re-bridge failure). Tears down any dead PC first.
   */
  const reconnectMedia = useCallback(async (): Promise<string | false> => {
    if (state === 'connecting') {
      log('reconnectMedia: already connecting — ignoring')
      return false
    }
    teardownPc()
    setState('connecting')
    setError(null)
    setCallId(null)
    log('reconnectMedia: start')
    try {
      log('step 1: getUserMedia(audio)')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      log('step 2: new RTCPeerConnection')
      const pc = new RTCPeerConnection({ iceServers: DEFAULT_ICE })
      pcRef.current = pc
      isClosingRef.current = false
      pendingLocalCandidates.current = []

      stream.getTracks().forEach((t) => pc.addTrack(t, stream))

      pc.ontrack = (ev) => {
        log('ontrack')
        const audio = ensureRemoteAudio()
        audio.srcObject = ev.streams[0]
      }
      pc.onconnectionstatechange = () => {
        log('connectionState →', pc.connectionState)
        if (pc.connectionState === 'failed' && !isClosingRef.current) {
          setError('ICE 连接失败（UDP 16384-32767 可能不通）')
          setState('failed')
        }
      }
      pc.onicecandidate = async (ev) => {
        if (!ev.candidate) return
        const cid = callIdRef.current
        if (!cid) {
          pendingLocalCandidates.current.push(ev.candidate)
          return
        }
        try {
          await postWebRTCIce(cid, {
            candidate: ev.candidate.candidate,
            sdp_mid: ev.candidate.sdpMid,
            sdp_m_line_index: ev.candidate.sdpMLineIndex,
          })
        } catch (e) {
          console.warn('[webrtc-leg] ice upstream failed', e)
        }
      }

      log('step 3: createOffer + setLocalDescription')
      const offer = await pc.createOffer({ offerToReceiveAudio: true })
      await pc.setLocalDescription(offer)

      log('step 4: POST /current-call/media-reconnect')
      const result = await reconnectCurrentCallMedia(offer.sdp ?? '')
      if (!result.call_id) {
        throw new Error('media_reconnect_no_call_id')
      }
      log('step 4 ✓ call_id=', result.call_id)
      callIdRef.current = result.call_id
      setCallId(result.call_id)

      for (const c of pendingLocalCandidates.current) {
        postWebRTCIce(result.call_id, {
          candidate: c.candidate,
          sdp_mid: c.sdpMid,
          sdp_m_line_index: c.sdpMLineIndex,
        }).catch(() => {})
      }
      pendingLocalCandidates.current = []

      log('step 5: setRemoteDescription(answer)')
      await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp || '' })
      setState('ready')
      log('reconnectMedia ✓ ready')
      return result.call_id
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e) || 'unknown error'
      console.error('[webrtc-leg] reconnectMedia FAILED:', e)
      setError(msg)
      setState('failed')
      teardownPc()
      return false
    }
  }, [ensureRemoteAudio, state, teardownPc])

  useEffect(() => () => goOffline(), [goOffline])

  return {
    state,
    callId,
    error,
    acceptOffer,
    originateOffer,
    reconnectMedia,
    goOffline,
    applyRemoteIce,
    setMuted,
  }
}
