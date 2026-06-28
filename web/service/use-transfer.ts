import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import { agentKeys, conversationKeys } from './use-conversations'
import type { Conversation } from '@/models/conversation'
import type {
  TransferTargetListResponse,
} from '@/models/transfer'

const NS = 'transfer'
const TARGET_REFRESH_INTERVAL_MS = 5_000

export const transferKeys = {
  all: [NS] as const,
  targets: (keyword: string, conversationId?: number) =>
    [...transferKeys.all, 'targets', keyword, conversationId ?? null] as const,
}

export const useTransferTargets = (
  keyword: string,
  enabled: boolean,
  conversationId?: number,
) =>
  useQuery({
    queryKey: transferKeys.targets(keyword.trim(), conversationId),
    queryFn: () => {
      // Send conversation_id so the server can also exclude that
      // conversation's current owner — covers the admin case where the
      // requester is not the owner.
      const searchParams: Record<string, string | number> = {}
      if (keyword.trim()) searchParams.keyword = keyword.trim()
      if (conversationId) searchParams.conversation_id = conversationId
      return get<TransferTargetListResponse>('v1/workspace/transfer-targets', {
        searchParams: Object.keys(searchParams).length ? searchParams : undefined,
      })
    },
    enabled,
    staleTime: TARGET_REFRESH_INTERVAL_MS,
    refetchInterval: enabled ? TARGET_REFRESH_INTERVAL_MS : false,
    refetchIntervalInBackground: false,
  })

export const useTransferConversation = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      conversationId,
      targetAgentId,
    }: {
      conversationId: number
      targetAgentId: number
    }) =>
      post<Conversation>(`v1/workspace/conversations/${conversationId}/transfer`, {
        json: { target_agent_id: targetAgentId },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}
