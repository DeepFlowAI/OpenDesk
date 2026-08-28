import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, filenameFromContentDisposition, get, getBlob, post, put } from './base'
import type {
  AgentStatusResponse,
  AgentStatusUpdate,
  ConsultableAgent,
  TransferQueue,
  CallRecordDetail,
  CallRecordFilterOptionsResponse,
  CallRecordListResponse,
  CallTrajectoryResponse,
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
  recordFilterOptions: () => [NS, 'records', 'filter-options'] as const,
  record: (publicId: string | null | undefined) => [NS, 'records', publicId ?? null] as const,
  transcript: (publicId: string | null | undefined) => [NS, 'records', publicId ?? null, 'transcript'] as const,
  trajectory: (publicId: string | null | undefined) => [NS, 'records', publicId ?? null, 'trajectory'] as const,
  satisfaction: () => [NS, 'current-call', 'satisfaction'] as const,
}

// Exported so socket handlers can invalidate every records query (list pages
// and the workspace sidebar) when a call ends, not just the sidebar's page.
export const callCenterQueryKeys = keys

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

export type CurrentCallActionResponse = {
  ok: boolean
  call_id?: string
  error?: string
  note?: string
  execution_id?: number
  flow_name?: string
  flow_version_no?: number
}

export type SatisfactionTriggerAvailability = {
  available: boolean
  reason: string | null
  message: string | null
}

export type CurrentCallSatisfactionAvailability = {
  call_id: string | null
  agent_invite: SatisfactionTriggerAvailability
  auto_transfer: SatisfactionTriggerAvailability
  flow: { id: number; name: string; version_no: number } | null
}

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

export const useCurrentCallSatisfaction = (enabled: boolean) =>
  useQuery({
    queryKey: keys.satisfaction(),
    queryFn: () =>
      get<CurrentCallSatisfactionAvailability>(
        'v1/call-center/agents/me/current-call/satisfaction',
      ),
    enabled,
    staleTime: 5_000,
    refetchInterval: enabled ? 15_000 : false,
  })

export const inviteCurrentCallSatisfaction = () =>
  post<CurrentCallActionResponse>(
    'v1/call-center/agents/me/current-call/satisfaction/invite',
  )

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

export type CallRecordsParams = {
  page?: number
  per_page?: number
  direction?: string
  call_source?: string
  lifecycle_status?: string
  finalization_status?: string
  actual_reception_type?: string
  call_result?: string
  hangup_party?: string
  hangup_reason_code?: string
  initiator_agent_id?: number
  last_serving_agent_id?: number
  user_id?: number
  last_queue_type?: string
  last_queue_id?: number
  recording_status?: string
  satisfaction_result?: string[]
  satisfaction_trigger_source?: string[]
  keyword?: string
  start_time?: string
  end_time?: string
  min_total_duration_ms?: number
  max_total_duration_ms?: number
  min_customer_ring_duration_ms?: number
  max_customer_ring_duration_ms?: number
  min_agent_wait_duration_ms?: number
  max_agent_wait_duration_ms?: number
  min_customer_agent_talk_duration_ms?: number
  max_customer_agent_talk_duration_ms?: number
}

function callRecordsSearchParams(params: CallRecordsParams): URLSearchParams {
  const searchParams = new URLSearchParams()
  for (const [key, rawValue] of Object.entries(params)) {
    if (rawValue === undefined) continue
    if (Array.isArray(rawValue)) {
      rawValue.forEach((value) => searchParams.append(key, value))
    } else {
      searchParams.set(key, String(rawValue))
    }
  }
  return searchParams
}

type CallRecordsQueryOptions = {
  enabled?: boolean
  refetchInterval?: number
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
        params ? { searchParams: callRecordsSearchParams(params) } : undefined,
      ),
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval,
  })

export const useCallRecordFilterOptions = (enabled = true) =>
  useQuery({
    queryKey: keys.recordFilterOptions(),
    queryFn: () =>
      get<CallRecordFilterOptionsResponse>('v1/call-center/call-records/filter-options'),
    enabled,
    staleTime: 60_000,
  })

export const downloadCallRecordsExport = async (params: CallRecordsParams) => {
  const exportParams = { ...params }
  delete exportParams.page
  delete exportParams.per_page
  const { blob, headers } = await getBlob('v1/call-center/call-records-export.csv', {
    searchParams: callRecordsSearchParams(exportParams),
  })
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'call-records.csv',
    ),
  }
}

export const useCallRecord = (publicId: string | null | undefined) =>
  useQuery({
    queryKey: keys.record(publicId),
    queryFn: () => get<CallRecordDetail>(`v1/call-center/call-records/${publicId}`),
    enabled: Boolean(publicId),
  })

export const useCallTrajectory = (
  publicId: string | null | undefined,
  enabled = true,
) =>
  useQuery({
    queryKey: keys.trajectory(publicId),
    queryFn: () => get<CallTrajectoryResponse>(`v1/call-center/call-records/${publicId}/trajectory`),
    enabled: enabled && Boolean(publicId),
    staleTime: 0,
    refetchInterval: (query) => query.state.data?.is_live ? 5_000 : false,
  })

export const useCallTranscript = (publicId: string | null | undefined) =>
  useQuery({
    queryKey: keys.transcript(publicId),
    queryFn: () =>
      get<CallTranscriptResponse>(`v1/call-center/call-records/${publicId}/transcript`),
    enabled: Boolean(publicId),
  })

export const useIdentifyCallRecordUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (publicId: string) =>
      post<CallUserAssociationResponse>(`v1/call-center/call-records/${publicId}/identify-user`),
    onSuccess: (_, publicId) => {
      qc.invalidateQueries({ queryKey: keys.record(publicId) })
      qc.invalidateQueries({ queryKey: keys.recordsRoot() })
    },
  })
}

export const useLinkCallRecordUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ publicId, userId }: { publicId: string; userId: number }) =>
      put<CallUserAssociationResponse>(`v1/call-center/call-records/${publicId}/associated-user`, {
        json: { user_id: userId },
      }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: keys.record(v.publicId) })
      qc.invalidateQueries({ queryKey: keys.recordsRoot() })
    },
  })
}
