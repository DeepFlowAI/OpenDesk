import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  CallPromptToneSettings,
  UpdateCallPromptTonesPayload,
} from '@/models/call-prompt-tone'

const NS = 'call-prompt-tones'

export const callPromptToneKeys = {
  all: [NS] as const,
  detail: () => [...callPromptToneKeys.all, 'detail'] as const,
}

export const useCallPromptTones = () =>
  useQuery({
    queryKey: callPromptToneKeys.detail(),
    queryFn: () =>
      get<CallPromptToneSettings>('v1/system-settings/call-prompt-tones'),
  })

export const useUpdateCallPromptTones = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UpdateCallPromptTonesPayload) =>
      put<CallPromptToneSettings>('v1/system-settings/call-prompt-tones', {
        json: data,
      }),
    onSuccess: (data) => {
      qc.setQueryData(callPromptToneKeys.detail(), data)
    },
  })
}
