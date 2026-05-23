import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ky from 'ky'
import { get, patch, post, put } from './base'
import type {
  PublicSatisfactionInvitation,
  PublicSatisfactionSubmitResponse,
  SatisfactionConversationState,
  SatisfactionFilterOptionsResponse,
  SatisfactionSubmissionPayload,
  SessionRecordSatisfactionResponse,
  SatisfactionSurveyConfig,
  SatisfactionSurveyVersionDetail,
  SatisfactionSurveyVersionListResponse,
  SaveSatisfactionSurveyPayload,
} from '@/models/satisfaction-survey'

const NS = 'satisfaction-survey'

export const satisfactionSurveyKeys = {
  all: [NS] as const,
  current: () => [...satisfactionSurveyKeys.all, 'current'] as const,
  conversation: (conversationId: number) => [...satisfactionSurveyKeys.all, 'conversation', conversationId] as const,
  publicInvitation: (conversationPublicId: string) =>
    [...satisfactionSurveyKeys.all, 'public-invitation', conversationPublicId] as const,
  sessionRecord: (recordId: number) => [...satisfactionSurveyKeys.all, 'session-record', recordId] as const,
  filterOptions: () => [...satisfactionSurveyKeys.all, 'filter-options'] as const,
  versions: () => [...satisfactionSurveyKeys.all, 'versions'] as const,
  versionList: (params: Record<string, unknown>) => [...satisfactionSurveyKeys.versions(), params] as const,
  version: (version: number) => [...satisfactionSurveyKeys.versions(), version] as const,
}

export const useSatisfactionSurveyConfig = () =>
  useQuery({
    queryKey: satisfactionSurveyKeys.current(),
    queryFn: () => get<SatisfactionSurveyConfig>('v1/conversation-settings/satisfaction'),
    retry: false,
  })

export const useSaveSatisfactionSurveyConfig = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveSatisfactionSurveyPayload) =>
      put<SatisfactionSurveyConfig>('v1/conversation-settings/satisfaction', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: satisfactionSurveyKeys.current() })
      qc.invalidateQueries({ queryKey: satisfactionSurveyKeys.versions() })
    },
  })
}

export const usePatchSatisfactionSurveyEnabled = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      patch<SatisfactionSurveyConfig>('v1/conversation-settings/satisfaction/enabled', { json: { enabled } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: satisfactionSurveyKeys.current() })
      qc.invalidateQueries({ queryKey: satisfactionSurveyKeys.versions() })
    },
  })
}

export const useSatisfactionSurveyVersions = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: satisfactionSurveyKeys.versionList(params ?? {}),
    queryFn: () =>
      get<SatisfactionSurveyVersionListResponse>('v1/conversation-settings/satisfaction/versions', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useSatisfactionSurveyVersion = (version: number | null) =>
  useQuery({
    queryKey: satisfactionSurveyKeys.version(version ?? 0),
    queryFn: () => get<SatisfactionSurveyVersionDetail>(`v1/conversation-settings/satisfaction/versions/${version}`),
    enabled: version != null,
  })

export const useConversationSatisfaction = (conversationId: number) =>
  useQuery({
    queryKey: satisfactionSurveyKeys.conversation(conversationId),
    queryFn: () => get<SatisfactionConversationState>(`v1/conversations/${conversationId}/satisfaction`),
    enabled: conversationId > 0,
    retry: false,
  })

export const useSendSatisfactionInvitation = (conversationId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params?: { force?: boolean }) =>
      post<SatisfactionConversationState>(
        `v1/conversations/${conversationId}/satisfaction/invitations`,
        { json: { force: params?.force ?? false } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: satisfactionSurveyKeys.conversation(conversationId) })
    },
  })
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })
const withVisitorToken = (visitorSessionToken: string) => ({
  Authorization: `Bearer ${visitorSessionToken}`,
})

export const fetchPublicSatisfactionInvitation = (params: {
  conversationPublicId: string
  visitorSessionToken: string
}) =>
  publicClient
    .get(`v1/public/conversations/${params.conversationPublicId}/satisfaction`, {
      headers: withVisitorToken(params.visitorSessionToken),
    })
    .json<PublicSatisfactionInvitation>()

export const createPublicSatisfactionInvitation = (params: {
  conversationPublicId: string
  visitorSessionToken: string
}) =>
  publicClient
    .post(`v1/public/conversations/${params.conversationPublicId}/satisfaction/invitations`, {
      headers: withVisitorToken(params.visitorSessionToken),
    })
    .json<PublicSatisfactionInvitation>()

export const submitPublicSatisfaction = (params: {
  conversationPublicId: string
  visitorSessionToken: string
  payload: SatisfactionSubmissionPayload
}) =>
  publicClient
    .post(`v1/public/conversations/${params.conversationPublicId}/satisfaction/submissions`, {
      headers: withVisitorToken(params.visitorSessionToken),
      json: params.payload,
    })
    .json<PublicSatisfactionSubmitResponse>()

export const useSessionRecordSatisfaction = (recordId: number) =>
  useQuery({
    queryKey: satisfactionSurveyKeys.sessionRecord(recordId),
    queryFn: () => get<SessionRecordSatisfactionResponse>(`v1/session-records/${recordId}/satisfaction`),
    enabled: recordId > 0,
  })

export const useSatisfactionFilterOptions = () =>
  useQuery({
    queryKey: satisfactionSurveyKeys.filterOptions(),
    queryFn: () => get<SatisfactionFilterOptionsResponse>('v1/session-records/satisfaction/filter-options'),
    retry: false,
  })
