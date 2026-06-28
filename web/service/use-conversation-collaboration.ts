import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import { conversationKeys } from './use-conversations'
import type {
  CollaborationInvitation,
  CollaborationInvitationListResponse,
  CollaborationInvitationRespondResponse,
  CollaborationTargetListResponse,
} from '@/models/conversation-collaboration'

const NS = 'conversation-collaboration'
const TARGET_REFRESH_INTERVAL_MS = 5_000

export const conversationCollaborationKeys = {
  all: [NS] as const,
  targets: (conversationId: number, keyword: string) =>
    [...conversationCollaborationKeys.all, 'targets', conversationId, keyword] as const,
  pending: () => [...conversationCollaborationKeys.all, 'pending'] as const,
}

export function setPendingCollaborationInvitationCache(
  queryClient: QueryClient,
  invitation: CollaborationInvitation,
) {
  queryClient.setQueryData<CollaborationInvitationListResponse>(
    conversationCollaborationKeys.pending(),
    (prev) => {
      const currentItems = prev?.items ?? []
      const withoutInvitation = currentItems.filter((item) => item.id !== invitation.id)
      if (invitation.status !== 'pending') {
        return { items: withoutInvitation, total: withoutInvitation.length }
      }
      const items = [invitation, ...withoutInvitation]
      return { items, total: items.length }
    },
  )
}

export const useCollaborationTargets = (
  conversationId: number,
  keyword: string,
  enabled: boolean,
) =>
  useQuery({
    queryKey: conversationCollaborationKeys.targets(conversationId, keyword.trim()),
    queryFn: () => {
      const searchParams: Record<string, string | number> = { conversation_id: conversationId }
      if (keyword.trim()) searchParams.keyword = keyword.trim()
      return get<CollaborationTargetListResponse>('v1/workspace/collaboration-targets', { searchParams })
    },
    enabled: enabled && conversationId > 0,
    staleTime: TARGET_REFRESH_INTERVAL_MS,
    refetchInterval: enabled && conversationId > 0 ? TARGET_REFRESH_INTERVAL_MS : false,
    refetchIntervalInBackground: false,
  })

export const usePendingCollaborationInvitations = (enabled: boolean) =>
  useQuery({
    queryKey: conversationCollaborationKeys.pending(),
    queryFn: () =>
      get<CollaborationInvitationListResponse>('v1/workspace/collaboration-invitations/pending'),
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  })

export const useCreateCollaborationInvitation = (conversationId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (inviteeId: number) =>
      post<CollaborationInvitation>(`v1/workspace/conversations/${conversationId}/collaboration-invitations`, {
        json: { invitee_id: inviteeId },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationCollaborationKeys.all })
    },
  })
}

export const useRespondCollaborationInvitation = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ invitationId, action }: { invitationId: number; action: 'accept' | 'decline' }) =>
      post<CollaborationInvitationRespondResponse>(
        `v1/workspace/collaboration-invitations/${invitationId}/respond`,
        { json: { action } },
      ),
    onSuccess: (_data, variables) => {
      qc.setQueryData<CollaborationInvitationListResponse>(
        conversationCollaborationKeys.pending(),
        (prev) => {
          if (!prev) return prev
          const items = prev.items.filter((item) => item.id !== variables.invitationId)
          return { ...prev, items, total: Math.max(0, prev.total - (prev.items.length - items.length)) }
        },
      )
      qc.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
    },
  })
}
