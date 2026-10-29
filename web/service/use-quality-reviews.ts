import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from '@/service/base'
import type {
  QualityDraftPayload,
  QualityReviewDetail,
  QualityReviewListResponse,
  QualityStatistics,
  QualityWorkbench,
} from '@/models/quality-review'

const NS = 'quality-reviews'
export const qualityReviewKeys = {
  all: [NS] as const,
  plan: (planId: number) => [NS, 'plan', planId] as const,
  list: (planId: number, params: object) => [NS, 'plan', planId, 'list', params] as const,
  pending: (planId: number, params: object) => [NS, 'plan', planId, 'pending', params] as const,
  stats: (planId: number) => [NS, 'plan', planId, 'stats'] as const,
  detail: (reviewId: number) => [NS, 'detail', reviewId] as const,
  workbench: (reviewId: number) => [NS, 'workbench', reviewId] as const,
}

export const useQualityReviews = (planId: number, params: { status?: string; source?: string; agent_id?: number; page?: number; per_page?: number }) => useQuery({
  queryKey: qualityReviewKeys.list(planId, params),
  queryFn: () => get<QualityReviewListResponse>(`v1/quality/online/plans/${planId}/reviews`, { searchParams: params }),
  enabled: planId > 0,
})

export const useMyPendingQualityReviews = (planId: number, params: { page?: number; per_page?: number }) => useQuery({
  queryKey: qualityReviewKeys.pending(planId, params),
  queryFn: () => get<QualityReviewListResponse>(`v1/quality/online/plans/${planId}/pending-mine`, { searchParams: params }),
  enabled: planId > 0,
})

export const useQualityStatistics = (planId: number) => useQuery({
  queryKey: qualityReviewKeys.stats(planId),
  queryFn: () => get<QualityStatistics>(`v1/quality/online/plans/${planId}/statistics`),
  enabled: planId > 0,
})

export const useQualityReviewDetail = (reviewId: number) => useQuery({
  queryKey: qualityReviewKeys.detail(reviewId),
  queryFn: () => get<QualityReviewDetail>(`v1/quality/online/reviews/${reviewId}`),
  enabled: reviewId > 0,
})

export const useQualityWorkbench = (reviewId: number) => useQuery({
  queryKey: qualityReviewKeys.workbench(reviewId),
  queryFn: () => get<QualityWorkbench>(`v1/quality/online/reviews/${reviewId}/workbench`),
  enabled: reviewId > 0,
})

function useReviewMutation<T, R>(fn: (value: T) => Promise<R>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qualityReviewKeys.all }),
  })
}

export const useMaterializeQualityPlan = () => useReviewMutation((planId: number) => post<{ created_reviews: number; queued_calls: number }>(`v1/quality/online/plans/${planId}/materialize`))
export const useOpenQualityReview = () => useReviewMutation((reviewId: number) => post<QualityWorkbench>(`v1/quality/online/reviews/${reviewId}/open`))
export const useSaveQualityDraft = () => useReviewMutation(({ reviewId, payload }: { reviewId: number; payload: QualityDraftPayload }) => put<QualityWorkbench>(`v1/quality/online/reviews/${reviewId}/draft`, { json: payload }))
export const useSubmitQualityReview = () => useReviewMutation(({ reviewId, payload }: { reviewId: number; payload: QualityDraftPayload }) => post<QualityReviewDetail>(`v1/quality/online/reviews/${reviewId}/submit`, { json: payload }))
export type QualityUnablePayload = QualityDraftPayload & { reason: string }
export const useSubmitUnableQualityReview = () => useReviewMutation(({ reviewId, payload }: { reviewId: number; payload: QualityUnablePayload }) => post<QualityReviewDetail>(`v1/quality/online/reviews/${reviewId}/submit-unable`, { json: payload }))
export const useReassignQualityReview = () => useReviewMutation(({ reviewId, reviewerId }: { reviewId: number; reviewerId: number }) => post(`v1/quality/online/reviews/${reviewId}/reassign`, { json: { reviewer_id: reviewerId } }))
export const useRetryQualityReview = () => useReviewMutation(({ planId, reviewId }: { planId: number; reviewId: number }) => post(`v1/quality/online/plans/${planId}/reviews/${reviewId}/retry`))
