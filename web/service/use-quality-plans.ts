import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from '@/service/base'
import type { QualityPlan, QualityPlanEstimate, QualityPlanListResponse, QualityPlanPayload, QualityPlanStatus } from '@/models/quality-plan'

const NS = 'quality-plans'
export const qualityPlanKeys = { all: [NS] as const, lists: () => [NS, 'list'] as const, list: (p: object) => [NS, 'list', p] as const, detail: (id: number) => [NS, 'detail', id] as const }
export const useQualityPlans = (params: { q?: string; status?: '' | QualityPlanStatus; run_mode?: string; page?: number; per_page?: number }) => useQuery({ queryKey: qualityPlanKeys.list(params), queryFn: () => get<QualityPlanListResponse>('v1/quality/online/plans', { searchParams: params }) })
export const useQualityPlan = (id: number) => useQuery({ queryKey: qualityPlanKeys.detail(id), queryFn: () => get<QualityPlan>(`v1/quality/online/plans/${id}`), enabled: id > 0 })
function usePlanMutation<T>(fn: (value: T) => Promise<QualityPlan>) { const qc = useQueryClient(); return useMutation({ mutationFn: fn, onSuccess: (plan) => { qc.setQueryData(qualityPlanKeys.detail(plan.id), plan); void qc.invalidateQueries({ queryKey: qualityPlanKeys.lists() }) } }) }
export const useCreateQualityPlan = () => usePlanMutation((payload: QualityPlanPayload) => post<QualityPlan>('v1/quality/online/plans', { json: payload }))
export const useUpdateQualityPlan = () => usePlanMutation(({ id, payload }: { id: number; payload: QualityPlanPayload }) => put<QualityPlan>(`v1/quality/online/plans/${id}`, { json: payload }))
export const useUpdateQualityPlanReviewers = () => usePlanMutation(({ id, reviewerIds }: { id: number; reviewerIds: number[] }) => put<QualityPlan>(`v1/quality/online/plans/${id}/reviewers`, { json: { reviewer_ids: reviewerIds } }))
export const useActivateQualityPlan = () => usePlanMutation((id: number) => post<QualityPlan>(`v1/quality/online/plans/${id}/activate`))
export const useTransitionQualityPlan = () => usePlanMutation(({ id, action }: { id: number; action: 'pause' | 'resume' }) => post<QualityPlan>(`v1/quality/online/plans/${id}/${action}`))
export function useEstimateQualityPlan() { const qc = useQueryClient(); return useMutation({ mutationFn: (id: number) => post<QualityPlanEstimate>(`v1/quality/online/plans/${id}/estimate`), onSuccess: (_result, id) => void qc.invalidateQueries({ queryKey: qualityPlanKeys.detail(id) }) }) }
