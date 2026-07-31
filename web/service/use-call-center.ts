import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  AgentStatusResponse,
  AgentStatusUpdate,
  ConsultableAgent,
  TransferQueue,
  CallRecordDetail,
  CallRecordListResponse,
  CallTranscriptResponse,
  CallUserAssociationResponse,
  WebRTCSession,
} from '@/models/call-center'

const NS = 'call-center'

const keys = {
  status: () => [NS, 'agent-status', 'me'] as const,
  session: () => [NS, 'webrtc-session', 'me'] as const,
  consultableAgents: (keyword: string) => [NS, 'consultable-agents', keyword] as const,
  transferQueues: (keyword: string) => [NS, 'transfer-queues', keyword] as const,
  recordsRoot: () => [NS, 'records'] as const,
  records: (params: Record<string, unknown>) => [NS, 'records', params] as const,
  record: (id: number | null | undefined) => [NS, 'records', id ?? null] as const,
  transcript: (id: number | null | undefined) => [NS, 'records', id ?? null, 'transcript'] as const,
}

/**
 * Workspace agents that can be a consult / transfer / conference target,
 * each with their live call-center status. `keyword` filters by name on the
 * server. Only enabled while a picker is open (pass `enabled`).
 */
export const useConsultableAgents = (keyword: string, enabled = true) =>
  useQuery({
    queryKey: keys.consultableAgents(keyword),
    queryFn: () =>
      get<ConsultableAgent[]>('v1/call-center/agents/consultable', {
        searchParams: keyword ? { keyword } : {},
      }),
    enabled,
    // The picker shows live agent reachability, so it must not serve the global
    // 60s cache: reopening always refetches, and while it's open we poll so a
    // colleague who just logged in (or dropped off) shows up without a full
    // page refresh. Polling only runs while the picker is open (enabled).
    staleTime: 0,
    refetchInterval: enabled ? 10_000 : false,
  })

/**
 * Employee-group queues available as a blind-transfer target, each with a
 * live available-agent count. `keyword` filters by queue name on the server.
 * Only enabled while the transfer picker's queue tab is open.
 */
export const useTransferQueues = (keyword: string, enabled = true) =>
  useQuery({
    queryKey: keys.transferQueues(keyword),
    queryFn: () =>
      get<TransferQueue[]>('v1/call-center/transfer-queues', {
        searchParams: keyword ? { keyword } : {},
      }),
    enabled,
    staleTime: 0,
    refetchInterval: enabled ? 10_000 : false,
  })

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

// Escape hatch: force-free a stranded call resource (e.g. after a lost
// call-end event) so the agent can switch status again.
export const useResetAgentStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      post<AgentStatusResponse>('v1/call-center/agent-status/me/reset', { json: {} }),
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

export type MediaReconnectResponse = {
  call_id: string
  sdp: string
  consult_active?: boolean
  consult_target_employee_id?: number | null
}

/** Rebuild the agent's WebRTC leg and bridge it back to the live customer. */
export const reconnectCurrentCallMedia = (sdp: string) =>
  post<MediaReconnectResponse>('v1/call-center/agents/me/current-call/media-reconnect', {
    json: { sdp },
  })

// ─────────── In-call control (hold / dtmf / transfer / consult / conference) ───────────

export type CallControlResult = { ok: boolean; note?: string | null; call_id?: string | null }

export type TransferTargetType = 'employee' | 'queue' | 'external'
export type ConsultTargetType = 'employee' | 'external'

export type CallControlTarget = {
  target_type: TransferTargetType
  target_id?: number | null
  number?: string | null
}

export const holdCurrentCall = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/hold')

export const unholdCurrentCall = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/unhold')

export const sendCurrentCallDtmf = (digits: string) =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/dtmf', {
    json: { digits },
  })

export const setCurrentCallMute = (muted: boolean) =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/mute', {
    json: { muted },
  })

export const transferCurrentCall = (target: CallControlTarget) =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/transfer', {
    json: target,
  })

export const startConsult = (target: { target_type: ConsultTargetType; target_id?: number | null; number?: string | null }) =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/consult', {
    json: target,
  })

export const endConsult = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/consult/end')

export const conferenceAdd = (target: { target_type: ConsultTargetType; target_id?: number | null; number?: string | null }) =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/conference/add', {
    json: target,
  })

export const conferenceMerge = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/conference/merge')

export const conferenceRemove = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/conference/remove')

export const conferenceLeave = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/conference/leave')

export const conferenceEndAll = () =>
  post<CallControlResult>('v1/call-center/agents/me/current-call/conference/end-all')

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

type CallRecordsParams = {
  page?: number
  per_page?: number
  direction?: string
  agent_id?: number
  user_id?: number
  keyword?: string
  start_time?: string
  end_time?: string
}

type CallRecordsQueryOptions = {
  enabled?: boolean
}

export const useCallRecords = (
  params?: CallRecordsParams,
  options?: CallRecordsQueryOptions,
) =>
  useQuery({
    queryKey: keys.records(params ?? {}),
    queryFn: () =>
      get<CallRecordListResponse>(
        'v1/call-center/call-records',
        params ? { searchParams: params as Record<string, string | number> } : undefined,
      ),
    enabled: options?.enabled ?? true,
  })

export const useCallRecord = (id: number | null | undefined) =>
  useQuery({
    queryKey: keys.record(id),
    queryFn: () => get<CallRecordDetail>(`v1/call-center/call-records/${id}`),
    enabled: typeof id === 'number',
  })

export const useCallTranscript = (id: number | null | undefined) =>
  useQuery({
    queryKey: keys.transcript(id),
    queryFn: () =>
      get<CallTranscriptResponse>(`v1/call-center/call-records/${id}/transcript`),
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
