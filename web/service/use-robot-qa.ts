import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  RobotQaCreatePayload,
  RobotQaCreateResponse,
  RobotQaDirectoryList,
  RobotQaKnowledgeBaseList,
  RobotQaRuntime,
  RobotQaSetting,
  RobotQaSettingPayload,
} from '@/models/robot-qa'
import { get, post, put } from '@/service/base'


const NS = 'robot-qa'

export const robotQaKeys = {
  all: [NS] as const,
  setting: () => [...robotQaKeys.all, 'setting'] as const,
  knowledgeBases: () => [...robotQaKeys.all, 'knowledge-bases'] as const,
  runtime: () => [...robotQaKeys.all, 'runtime'] as const,
  directories: (knowledgeBaseId?: number | null) =>
    [...robotQaKeys.all, 'directories', knowledgeBaseId ?? null] as const,
}

export const useRobotQaSetting = () =>
  useQuery({
    queryKey: robotQaKeys.setting(),
    queryFn: () => get<RobotQaSetting>('v1/conversation-settings/robot-qa'),
    retry: false,
  })

export const useRobotQaKnowledgeBases = () =>
  useQuery({
    queryKey: robotQaKeys.knowledgeBases(),
    queryFn: () => get<RobotQaKnowledgeBaseList>('v1/conversation-settings/robot-qa/knowledge-bases'),
    retry: false,
  })

export const useRobotQaRuntime = (enabled = true) =>
  useQuery({
    queryKey: robotQaKeys.runtime(),
    queryFn: () => get<RobotQaRuntime>('v1/conversation-settings/robot-qa/runtime'),
    enabled,
    retry: false,
    staleTime: 30_000,
  })

export const useRobotQaDirectories = (enabled = true, knowledgeBaseId?: number | null) =>
  useQuery({
    queryKey: robotQaKeys.directories(knowledgeBaseId),
    queryFn: () => get<RobotQaDirectoryList>('v1/conversation-settings/robot-qa/directories'),
    enabled,
    retry: false,
  })

export const useCreateRobotQa = (conversationId: number, messageId: number) =>
  useMutation({
    mutationFn: (payload: RobotQaCreatePayload) =>
      post<RobotQaCreateResponse>(
        `v1/conversations/${conversationId}/messages/${messageId}/robot-qa`,
        { json: payload },
      ),
  })

export const useSaveRobotQaSetting = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: RobotQaSettingPayload) =>
      put<RobotQaSetting>('v1/conversation-settings/robot-qa', { json: payload }),
    onSuccess: (setting) => {
      queryClient.setQueryData(robotQaKeys.setting(), setting)
      queryClient.invalidateQueries({ queryKey: robotQaKeys.runtime() })
      queryClient.invalidateQueries({ queryKey: [...robotQaKeys.all, 'directories'] })
    },
  })
}
