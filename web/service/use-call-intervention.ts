import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '@/service/base'
import type {
  InterventionReasonPayload,
  InterventionResult,
  LiveCallsResponse,
} from '@/models/call-intervention'

// Live-call table refreshes on a 10s full recalibration.
const LIVE_REFRESH_MS = 10_000

export const liveCallKeys = {
  all: ['call-monitor-live'] as const,
}

export const useLiveCalls = (enabled = true) =>
  useQuery({
    queryKey: liveCallKeys.all,
    queryFn: () => get<LiveCallsResponse>('v1/reports/call-monitor/live/calls'),
    enabled,
    refetchInterval: LIVE_REFRESH_MS,
    refetchIntervalInBackground: false,
    staleTime: LIVE_REFRESH_MS - 1_000,
  })

const base = (callId: string) => `v1/reports/call-monitor/live/calls/${callId}`

export type SupervisorWebRTCOffer = {
  call_id: string
  supervisor_call_id: string
  sdp: string
}

/**
 * Negotiate the supervisor's own WebRTC media leg for a monitored call. Must
 * run before whisper / barge / takeover so the supervisor is audible.
 */
export const postSupervisorWebRTCOffer = (callId: string, sdp: string) =>
  post<SupervisorWebRTCOffer>(`${base(callId)}/webrtc/offer`, { json: { sdp } })

type SupervisorIceCandidate = {
  candidate: string
  sdp_mid: string | null
  sdp_m_line_index: number | null
}

/**
 * Trickle one browser ICE candidate for the supervisor's media leg. `callId` is
 * the target call id (as with the other endpoints); the backend resolves the
 * supervisor leg from the monitor holder.
 */
export const postSupervisorIce = (callId: string, candidate: SupervisorIceCandidate) =>
  post(`${base(callId)}/webrtc/ice`, { json: candidate })

export const useListenCall = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (callId: string) => post<InterventionResult>(`${base(callId)}/listen`),
    onSettled: () => qc.invalidateQueries({ queryKey: liveCallKeys.all }),
  })
}

export const useWhisperCall = () =>
  useMutation({
    mutationFn: (callId: string) => post<InterventionResult>(`${base(callId)}/whisper`),
  })

export const useBargeCall = () =>
  useMutation({
    mutationFn: (callId: string) => post<InterventionResult>(`${base(callId)}/barge`),
  })

export const useTakeoverCall = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ callId, payload }: { callId: string; payload: InterventionReasonPayload }) =>
      post<InterventionResult>(`${base(callId)}/takeover`, { json: payload }),
    onSettled: () => qc.invalidateQueries({ queryKey: liveCallKeys.all }),
  })
}

export const useForceHangupCall = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ callId, payload }: { callId: string; payload: InterventionReasonPayload }) =>
      post<InterventionResult>(`${base(callId)}/force-hangup`, { json: payload }),
    onSettled: () => qc.invalidateQueries({ queryKey: liveCallKeys.all }),
  })
}

// End a call the supervisor has taken over (hangs up the customer). Distinct
// from stop (which only exits monitoring) and force-hangup (which needs a
// reason and ends any call's whole chain).
export const useEndTakeover = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (callId: string) => post<InterventionResult>(`${base(callId)}/takeover/hangup`),
    onSettled: () => qc.invalidateQueries({ queryKey: liveCallKeys.all }),
  })
}

export const useStopMonitoring = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (callId: string) => post<InterventionResult>(`${base(callId)}/stop`),
    onSettled: () => qc.invalidateQueries({ queryKey: liveCallKeys.all }),
  })
}
