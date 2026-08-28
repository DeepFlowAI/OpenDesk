import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  PersonalAutoOutboundConfig,
  PersonalAutoOutboundSession,
  PersonalAutoOutboundSessionEnvelope,
  PersonalAutoOutboundStart,
  PersonalOutboundRecording,
} from '@/models/personal-auto-outbound'
import { del, get, patch, post, postForm } from '@/service/base'
import type {
  AutoOutboundAgentContext,
  AutoOutboundWrapupPayload,
} from '@/models/auto-outbound-task'

const configKey = ['personal-auto-outbound', 'config'] as const
const sessionKey = ['personal-auto-outbound', 'session'] as const

export const usePersonalAutoOutboundConfig = () =>
  useQuery({
    queryKey: configKey,
    queryFn: () => get<PersonalAutoOutboundConfig>('v1/call-center/personal-auto-outbound/config'),
    refetchOnMount: 'always',
  })

export const useCurrentPersonalAutoOutboundSession = () =>
  useQuery({
    queryKey: sessionKey,
    queryFn: () => get<PersonalAutoOutboundSessionEnvelope>('v1/call-center/personal-auto-outbound/sessions/current'),
    refetchInterval: 2000,
  })

export const useUploadPersonalOutboundRecording = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, file }: { type: 'opening' | 'closing'; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return postForm<PersonalOutboundRecording>(`v1/call-center/personal-auto-outbound/recordings/${type}`, form)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: configKey }),
  })
}

export const useControlPersonalAutoOutboundSession = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, action }: { sessionId: number; action: 'pause' | 'resume' | 'stop' }) =>
      post<PersonalAutoOutboundSession>(`v1/call-center/personal-auto-outbound/sessions/${sessionId}/${action}`),
    onSuccess: (session) => {
      queryClient.setQueryData<PersonalAutoOutboundSessionEnvelope>(sessionKey, (current) =>
        current ? { ...current, session } : current,
      )
      queryClient.invalidateQueries({ queryKey: sessionKey })
      queryClient.invalidateQueries({ queryKey: configKey })
    },
  })
}

export const usePersonalAutoOutboundBusinessContext = (callId: number, enabled = true) =>
  useQuery({
    queryKey: [...sessionKey, 'business-context', callId] as const,
    queryFn: () =>
      get<AutoOutboundAgentContext>(
        `v1/call-center/personal-auto-outbound/calls/${callId}/business-context`,
      ),
    enabled: enabled && Number.isFinite(callId) && callId > 0,
  })

export const useSubmitPersonalAutoOutboundWrapup = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ callId, data }: { callId: number; data: AutoOutboundWrapupPayload }) =>
      post<{ id: number; target_id: number; field_values: Record<string, unknown> }>(
        `v1/call-center/personal-auto-outbound/calls/${callId}/wrapup`,
        { json: data },
      ),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: [...sessionKey, 'business-context', variables.callId] })
      queryClient.invalidateQueries({ queryKey: sessionKey })
    },
  })
}

export const useSavePersonalOutboundOpeningScript = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (scriptText: string | null) =>
      patch<PersonalOutboundRecording>('v1/call-center/personal-auto-outbound/recordings/opening/script', {
        json: { script_text: scriptText },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: configKey }),
  })
}

export const useRemovePersonalOutboundRecording = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (type: 'opening' | 'closing') =>
      del<{ removed: boolean }>(`v1/call-center/personal-auto-outbound/recordings/${type}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: configKey }),
  })
}

export const useStartPersonalAutoOutboundSession = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: PersonalAutoOutboundStart) =>
      post<PersonalAutoOutboundSession>('v1/call-center/personal-auto-outbound/sessions', { json: data }),
    onSuccess: (session) => {
      queryClient.setQueryData<PersonalAutoOutboundSessionEnvelope>(sessionKey, {
        session,
        metrics: {
          ringing_current: 0,
          ringing_total: 0,
          screening_current: 0,
          screening_total: 0,
          human_current: 0,
          human_total: 0,
          filtered_current: 0,
          filtered_total: 0,
        },
        calls: [],
        gate_reason: null,
      })
      queryClient.invalidateQueries({ queryKey: sessionKey })
      queryClient.invalidateQueries({ queryKey: configKey })
    },
  })
}
