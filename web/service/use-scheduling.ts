import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, filenameFromContentDisposition, get, getBlob, post, put } from './base'
import type {
  AssignmentBulkCreatePayload,
  AssignmentBulkCreateResponse,
  AssignmentBulkDeleteResponse,
  AssignmentListResponse,
  CopyWeekPayload,
  CopyWeekResponse,
  MessageResponse,
  MySchedule,
  PoolMemberListResponse,
  PublishResetResult,
  PublishStatus,
  ShiftCreatePayload,
  ShiftListResponse,
  Shift,
  ShiftUpdatePayload,
} from '@/models/scheduling'
import type {
  GenerateApplyResponse,
  GeneratePayload,
  GeneratePreviewResponse,
  ViolationListResponse,
} from '@/models/scheduling-rule'

const NS = 'scheduling'

export const schedulingKeys = {
  all: [NS] as const,
  shifts: () => [...schedulingKeys.all, 'shifts'] as const,
  pool: (groupIds: number[]) =>
    [...schedulingKeys.all, 'pool', [...groupIds].sort((a, b) => a - b)] as const,
  assignments: (startDate: string, endDate: string) =>
    [...schedulingKeys.all, 'assignments', startDate, endDate] as const,
  violations: (startDate: string, endDate: string, groupIds: number[]) =>
    [
      ...schedulingKeys.all,
      'violations',
      startDate,
      endDate,
      [...groupIds].sort((a, b) => a - b),
    ] as const,
  publishStatus: (date: string) => [...schedulingKeys.all, 'publish-status', date] as const,
  mySchedule: (week?: string) => [...schedulingKeys.all, 'my-schedule', week ?? 'current'] as const,
}

export function useMySchedule(week?: string, enabled = true) {
  return useQuery({
    queryKey: schedulingKeys.mySchedule(week),
    queryFn: () =>
      get<MySchedule>('v1/scheduling/me', {
        searchParams: week ? { week } : undefined,
      }),
    enabled,
    retry: false,
  })
}

export function useShifts(enabled = true) {
  return useQuery({
    queryKey: schedulingKeys.shifts(),
    queryFn: () => get<ShiftListResponse>('v1/scheduling/shifts'),
    enabled,
  })
}

function useInvalidateShifts() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: schedulingKeys.shifts() })
}

export function useCreateShift() {
  const invalidate = useInvalidateShifts()
  return useMutation({
    mutationFn: (payload: ShiftCreatePayload) =>
      post<Shift>('v1/scheduling/shifts', { json: payload }),
    onSuccess: invalidate,
  })
}

export function useUpdateShift() {
  const invalidate = useInvalidateShifts()
  return useMutation({
    mutationFn: ({ id, ...payload }: ShiftUpdatePayload & { id: number }) =>
      put<Shift>(`v1/scheduling/shifts/${id}`, { json: payload }),
    onSuccess: invalidate,
  })
}

export function useDeleteShift() {
  const invalidate = useInvalidateShifts()
  return useMutation({
    mutationFn: (id: number) => del<MessageResponse>(`v1/scheduling/shifts/${id}`),
    onSuccess: invalidate,
  })
}

export function usePoolMembers(groupIds: number[], enabled = true) {
  return useQuery({
    queryKey: schedulingKeys.pool(groupIds),
    queryFn: () =>
      get<PoolMemberListResponse>('v1/scheduling/pool-members', {
        searchParams: groupIds.map((id) => ['group_ids', String(id)]),
      }),
    enabled: enabled && groupIds.length > 0,
  })
}

export function useAssignments(startDate: string, endDate: string, enabled = true) {
  return useQuery({
    queryKey: schedulingKeys.assignments(startDate, endDate),
    queryFn: () =>
      get<AssignmentListResponse>('v1/scheduling/assignments', {
        searchParams: { start_date: startDate, end_date: endDate },
      }),
    enabled: enabled && Boolean(startDate) && Boolean(endDate),
  })
}

function useInvalidateAssignments() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: [...schedulingKeys.all, 'assignments'] })
    queryClient.invalidateQueries({ queryKey: [...schedulingKeys.all, 'violations'] })
    queryClient.invalidateQueries({ queryKey: [...schedulingKeys.all, 'publish-status'] })
  }
}

export function useCreateAssignments() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (payload: AssignmentBulkCreatePayload) =>
      post<AssignmentBulkCreateResponse>('v1/scheduling/assignments', { json: payload }),
    onSuccess: invalidate,
  })
}

export function useDeleteAssignments() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (ids: number[]) =>
      del<AssignmentBulkDeleteResponse>('v1/scheduling/assignments', { json: { ids } }),
    onSuccess: invalidate,
  })
}

export function useCopyWeek() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (payload: CopyWeekPayload) =>
      post<CopyWeekResponse>('v1/scheduling/assignments/copy-week', { json: payload }),
    onSuccess: invalidate,
  })
}

export function useViolations(
  startDate: string,
  endDate: string,
  groupIds: number[],
  enabled = true,
) {
  return useQuery({
    queryKey: schedulingKeys.violations(startDate, endDate, groupIds),
    queryFn: () =>
      get<ViolationListResponse>('v1/scheduling/violations', {
        searchParams: [
          ['start_date', startDate],
          ['end_date', endDate],
          ...groupIds.map((id): [string, string] => ['group_ids', String(id)]),
        ],
      }),
    enabled: enabled && Boolean(startDate) && Boolean(endDate) && groupIds.length > 0,
  })
}

export function useGeneratePreview() {
  return useMutation({
    mutationFn: (payload: GeneratePayload) =>
      post<GeneratePreviewResponse>('v1/scheduling/generate/preview', { json: payload }),
  })
}

export function useGenerateApply() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (payload: GeneratePayload) =>
      post<GenerateApplyResponse>('v1/scheduling/generate/apply', { json: payload }),
    onSuccess: invalidate,
  })
}

export function usePublishStatus(date: string, enabled = true) {
  return useQuery({
    queryKey: schedulingKeys.publishStatus(date),
    queryFn: () =>
      get<PublishStatus>('v1/scheduling/publish-status', {
        searchParams: { date },
      }),
    enabled: enabled && Boolean(date),
    retry: false,
  })
}

export function usePublishWeek() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (date: string) =>
      post<PublishStatus>('v1/scheduling/publish', { json: { date } }),
    onSuccess: invalidate,
  })
}

export function useResetWeek() {
  const invalidate = useInvalidateAssignments()
  return useMutation({
    mutationFn: (date: string) =>
      post<PublishResetResult>('v1/scheduling/reset', { json: { date } }),
    onSuccess: invalidate,
  })
}

export async function exportSchedulingAssignments(params: {
  startDate: string
  endDate: string
  groupIds: number[]
}) {
  const searchParams = new URLSearchParams({
    start_date: params.startDate,
    end_date: params.endDate,
  })
  for (const id of params.groupIds) {
    searchParams.append('group_ids', String(id))
  }
  const { blob, headers } = await getBlob(`v1/scheduling/export.xlsx?${searchParams}`, {
    timeout: 120000,
  })
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'scheduling.xlsx',
    ),
  }
}
