import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  AgentStatusResponse,
  AgentStatusUpdate,
  CallRecordDetail,
  CallRecordListResponse,
  CallUserAssociationResponse,
  WebRTCSession,
} from '@/models/call-center'

const NS = 'call-center'

const keys = {
  status: () => [NS, 'agent-status', 'me'] as const,
  session: () => [NS, 'webrtc-session', 'me'] as const,
  recordsRoot: () => [NS, 'records'] as const,
  records: (params: Record<string, unknown>) => [NS, 'records', params] as const,
  record: (id: number | null | undefined) => [NS, 'records', id ?? null] as const,
}

export const useMyAgentStatus = () =>
  useQuery({
    queryKey: keys.status(),
    queryFn: () => get<AgentStatusResponse>('v1/call-center/agent-status/me'),
    refetchInterval: 30_000,
  })

export const useSetAgentStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AgentStatusUpdate) =>
      put<AgentStatusResponse>('v1/call-center/agent-status/me', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.status() }),
  })
}

export const useMyWebRTCSession = () =>
  useQuery({
    queryKey: keys.session(),
    queryFn: () => get<WebRTCSession | null>('v1/call-center/agents/me/webrtc-session'),
  })

export const useOpenWebRTCSession = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (webrtc_call_id: string) =>
      post<WebRTCSession>('v1/call-center/agents/me/webrtc-session', {
        json: { webrtc_call_id },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.session() }),
  })
}

export const useCloseWebRTCSession = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => del('v1/call-center/agents/me/webrtc-session'),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.session() }),
  })
}

// ─────────── WebRTC signaling ───────────

export type WebRTCOfferResponse = { call_id: string; sdp: string }

export const postWebRTCOffer = (sdp: string) =>
  post<WebRTCOfferResponse>('v1/call-center/agents/me/webrtc/offer', {
    json: { sdp },
  })

export const postWebRTCIce = (
  call_id: string,
  candidate: { candidate: string; sdp_mid: string | null; sdp_m_line_index: number | null },
) =>
  post<{ ok: true }>('v1/call-center/agents/me/webrtc/ice', {
    json: { call_id, candidate },
  })

// ─────────── Current-call control ───────────

export type CurrentCallActionResponse = { ok: boolean; call_id?: string; error?: string }

export type AcceptOfferResponse = {
  ok: boolean
  call_id?: string
  sdp?: string
  error?: string
}

export const acceptCurrentCall = (body: { offer_id: string; sdp: string }) =>
  post<AcceptOfferResponse>('v1/call-center/agents/me/current-call/accept', {
    json: body,
  })

export const rejectCurrentCall = (offerId: string) =>
  post<CurrentCallActionResponse>('v1/call-center/agents/me/current-call/reject', {
    json: { offer_id: offerId },
  })

export const hangupCurrentCall = () =>
  post<CurrentCallActionResponse>('v1/call-center/agents/me/current-call/hangup')

export type DialOutboundResponse = {
  call_id: string
  conversation_id?: string | null
  status: string
}

export const dialOutbound = (body: {
  outbound_phone_number_id: string
  destination: string
}) =>
  post<DialOutboundResponse>('v1/call-center/agents/me/dial', {
    json: body,
  })

export type DialWebRTCOfferResponse = {
  webrtc_call_id: string
  sdp: string
}

export const dialWebRTCOffer = (body: {
  outbound_call_id: string
  sdp: string
}) =>
  post<DialWebRTCOfferResponse>('v1/call-center/agents/me/dial-webrtc/offer', {
    json: body,
  })

/**
 * Cancel an in-flight outbound call started by /dial. Idempotent and
 * accepts already-ended call_ids — safe to call as an "always cancel
 * + reset UI" path without checking SIP state first.
 */
export const cancelOutboundCall = (callId: string) =>
  post<{ ok: boolean }>('v1/call-center/agents/me/dial/cancel', {
    json: { call_id: callId },
  })

export const useCallRecords = (params?: {
  page?: number
  per_page?: number
  direction?: string
  agent_id?: number
  user_id?: number
  keyword?: string
  start_time?: string
  end_time?: string
}) =>
  useQuery({
    queryKey: keys.records(params ?? {}),
    queryFn: () =>
      get<CallRecordListResponse>('v1/call-center/call-records', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useCallRecord = (id: number | null | undefined) =>
  useQuery({
    queryKey: keys.record(id),
    queryFn: () => get<CallRecordDetail>(`v1/call-center/call-records/${id}`),
    enabled: typeof id === 'number',
  })

export const useIdentifyCallRecordUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (recordId: number) =>
      post<CallUserAssociationResponse>(`v1/call-center/call-records/${recordId}/identify-user`),
    onSuccess: (_, recordId) => {
      qc.invalidateQueries({ queryKey: keys.record(recordId) })
      qc.invalidateQueries({ queryKey: keys.recordsRoot() })
    },
  })
}

export const useLinkCallRecordUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ recordId, userId }: { recordId: number; userId: number }) =>
      put<CallUserAssociationResponse>(`v1/call-center/call-records/${recordId}/associated-user`, {
        json: { user_id: userId },
      }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: keys.record(v.recordId) })
      qc.invalidateQueries({ queryKey: keys.recordsRoot() })
    },
  })
}
