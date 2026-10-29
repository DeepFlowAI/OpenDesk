import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '@/service/base'
import type {
  QualityScorecard,
  QualityScorecardCreatePayload,
  QualityScorecardListResponse,
  QualityScorecardPayload,
  QualityScorecardStatus,
} from '@/models/quality-scorecard'

const NS = 'quality-scorecards'

export const qualityScorecardKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (params: Record<string, unknown>) => [NS, 'list', params] as const,
  details: () => [NS, 'detail'] as const,
  detail: (id: number) => [NS, 'detail', id] as const,
}

export type QualityScorecardListParams = {
  q?: string
  status?: '' | QualityScorecardStatus
  page?: number
  per_page?: number
}

export const useQualityScorecards = (params: QualityScorecardListParams) => useQuery({
  queryKey: qualityScorecardKeys.list(params),
  queryFn: () => get<QualityScorecardListResponse>('v1/quality/online/scorecards', { searchParams: params }),
})

export const useQualityScorecard = (id: number) => useQuery({
  queryKey: qualityScorecardKeys.detail(id),
  queryFn: () => get<QualityScorecard>(`v1/quality/online/scorecards/${id}`),
  enabled: id > 0,
})

function useScorecardMutation<TVariables>(mutationFn: (variables: TVariables) => Promise<QualityScorecard>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (scorecard) => {
      queryClient.setQueryData(qualityScorecardKeys.detail(scorecard.id), scorecard)
      void queryClient.invalidateQueries({ queryKey: qualityScorecardKeys.lists() })
    },
  })
}

export const useCreateQualityScorecard = () => useScorecardMutation(
  (payload: QualityScorecardCreatePayload) => post<QualityScorecard>('v1/quality/online/scorecards', { json: payload }),
)

export const useUpdateQualityScorecard = () => useScorecardMutation(
  ({ id, payload }: { id: number; payload: QualityScorecardPayload }) => (
    patch<QualityScorecard>(`v1/quality/online/scorecards/${id}`, { json: payload })
  ),
)

export const usePublishQualityScorecard = () => useScorecardMutation(
  (id: number) => post<QualityScorecard>(`v1/quality/online/scorecards/${id}/publish`),
)

export const useCreateQualityScorecardVersion = () => useScorecardMutation(
  (id: number) => post<QualityScorecard>(`v1/quality/online/scorecards/${id}/versions`),
)

export const useDisableQualityScorecardVersion = () => useScorecardMutation(
  ({ id, version }: { id: number; version: number }) => (
    post<QualityScorecard>(`v1/quality/online/scorecards/${id}/versions/${version}/disable`)
  ),
)
