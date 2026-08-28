import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  AdminExamListResponse,
  AttemptDetailResponse,
  AttemptStartResponse,
  AttemptSubmitResponse,
  ExamQuestionPayload,
  ExamResultListResponse,
  ExamStatus,
  LearningExam,
  LearningExamDetail,
  LearningExamQuestion,
  MyExamListResponse,
  MyExamSummary,
} from '@/models/learning-exam'
import type {
  AssignableEmployeeListResponse,
  AssignableGroupItem,
  AssignmentItem,
  AssignmentTargetType,
} from '@/models/learning'

const NS = 'learning-exam'

type Params = Record<string, string | number | undefined>

function toSearchParams(params?: Params): Record<string, string | number> {
  if (!params) return {}
  return Object.fromEntries(
    Object.entries(params).filter(
      (entry): entry is [string, string | number] =>
        entry[1] !== undefined && entry[1] !== '',
    ),
  ) as Record<string, string | number>
}

export const learningExamKeys = {
  all: [NS] as const,
  adminExams: (params: Params) => [...learningExamKeys.all, 'admin-exams', params] as const,
  exam: (id: number | null | undefined) => [...learningExamKeys.all, 'exam', id] as const,
  assignments: (examId: number) => [...learningExamKeys.all, 'assignments', examId] as const,
  assignableGroups: (examId: number, q?: string) =>
    [...learningExamKeys.all, 'assignable-groups', examId, q ?? ''] as const,
  assignableEmployees: (examId: number, params: Params) =>
    [...learningExamKeys.all, 'assignable-employees', examId, params] as const,
  results: (examId: number, params: Params) =>
    [...learningExamKeys.all, 'results', examId, params] as const,
  myExams: (params: Params) => [...learningExamKeys.all, 'my-exams', params] as const,
  myExam: (id: number | null | undefined) => [...learningExamKeys.all, 'my-exam', id] as const,
  attempt: (id: number | null | undefined) => [...learningExamKeys.all, 'attempt', id] as const,
}

function useInvalidateExam() {
  const queryClient = useQueryClient()
  return (examId: number) => invalidateExamQueries(queryClient, examId)
}

function invalidateExamQueries(queryClient: ReturnType<typeof useQueryClient>, examId: number) {
  queryClient.invalidateQueries({ queryKey: learningExamKeys.exam(examId) })
  queryClient.invalidateQueries({ queryKey: [NS, 'admin-exams'] })
  queryClient.invalidateQueries({ queryKey: learningExamKeys.assignments(examId) })
  queryClient.invalidateQueries({ queryKey: [NS, 'results', examId] })
  queryClient.invalidateQueries({ queryKey: [NS, 'assignable-groups', examId] })
  queryClient.invalidateQueries({ queryKey: [NS, 'assignable-employees', examId] })
}

function invalidateMyExamQueries(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: [NS, 'my-exams'] })
  queryClient.invalidateQueries({ queryKey: [NS, 'my-exam'] })
}

// ---------------------------------------------------------------------------
// Admin: exams
// ---------------------------------------------------------------------------

export interface AdminExamListParams {
  page?: number
  per_page?: number
  q?: string
  status?: ExamStatus | ''
}

export const useAdminExams = (params?: AdminExamListParams) =>
  useQuery({
    queryKey: learningExamKeys.adminExams((params ?? {}) as Params),
    queryFn: () =>
      get<AdminExamListResponse>('v1/learning/admin/exams', {
        searchParams: toSearchParams(params as Params),
      }),
    placeholderData: (prev) => prev,
  })

export const useAdminExam = (id: number | null | undefined) =>
  useQuery({
    queryKey: learningExamKeys.exam(id),
    queryFn: () => get<LearningExamDetail>(`v1/learning/admin/exams/${id}`),
    enabled: typeof id === 'number',
  })

export const useCreateExam = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name?: string }) =>
      post<LearningExam>('v1/learning/admin/exams', { json: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [NS, 'admin-exams'] }),
  })
}

export interface ExamUpdatePayload {
  name?: string
  intro?: string
  pass_percent?: number
  time_limit_minutes?: number | null
  max_attempts?: number
  shuffle_questions?: boolean
}

export const useUpdateExam = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (payload: ExamUpdatePayload) =>
      put<LearningExam>(`v1/learning/admin/exams/${examId}`, { json: payload }),
    onSuccess: () => invalidate(examId),
  })
}

export const usePublishExam = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (examId: number) =>
      post<LearningExam>(`v1/learning/admin/exams/${examId}/publish`),
    onSuccess: (_data, examId) => invalidateExamQueries(queryClient, examId),
  })
}

export const useUnpublishExam = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (examId: number) =>
      post<LearningExam>(`v1/learning/admin/exams/${examId}/unpublish`),
    onSuccess: (_data, examId) => invalidateExamQueries(queryClient, examId),
  })
}

export const useDeleteExam = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (examId: number) => del(`v1/learning/admin/exams/${examId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [NS, 'admin-exams'] }),
  })
}

// ---------------------------------------------------------------------------
// Admin: questions
// ---------------------------------------------------------------------------

export const useCreateQuestion = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (payload: ExamQuestionPayload) =>
      post<LearningExamQuestion>(`v1/learning/admin/exams/${examId}/questions`, { json: payload }),
    onSuccess: () => invalidate(examId),
  })
}

export const useUpdateQuestion = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: ({ questionId, payload }: { questionId: number; payload: ExamQuestionPayload }) =>
      put<LearningExamQuestion>(`v1/learning/admin/exam-questions/${questionId}`, {
        json: payload,
      }),
    onSuccess: () => invalidate(examId),
  })
}

export const useReorderQuestions = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (orderedIds: number[]) =>
      put(`v1/learning/admin/exams/${examId}/questions/order`, {
        json: { ordered_ids: orderedIds },
      }),
    onSuccess: () => invalidate(examId),
  })
}

export const useDeleteQuestion = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (questionId: number) => del(`v1/learning/admin/exam-questions/${questionId}`),
    onSuccess: () => invalidate(examId),
  })
}

// ---------------------------------------------------------------------------
// Admin: visibility, assignments & results
// ---------------------------------------------------------------------------

export const useUpdateExamVisibility = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (visibility: 'all' | 'assigned') =>
      put<LearningExam>(`v1/learning/admin/exams/${examId}/visibility`, {
        json: { visibility },
      }),
    onSuccess: () => invalidate(examId),
  })
}

export const useExamAssignments = (examId: number | null | undefined) =>
  useQuery({
    queryKey: learningExamKeys.assignments(examId ?? 0),
    queryFn: () =>
      get<{ items: AssignmentItem[] }>(`v1/learning/admin/exams/${examId}/assignments`),
    enabled: typeof examId === 'number',
  })

export const useAddExamAssignments = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (targets: { target_type: AssignmentTargetType; target_id: number }[]) =>
      post<{ added_count: number }>(`v1/learning/admin/exams/${examId}/assignments`, {
        json: { targets },
      }),
    onSuccess: () => invalidate(examId),
  })
}

export const useRemoveExamAssignment = (examId: number) => {
  const invalidate = useInvalidateExam()
  return useMutation({
    mutationFn: (assignmentId: number) =>
      del(`v1/learning/admin/exams/${examId}/assignments/${assignmentId}`),
    onSuccess: () => invalidate(examId),
  })
}

export const useExamAssignableGroups = (examId: number | null, q: string, enabled: boolean) =>
  useQuery({
    queryKey: learningExamKeys.assignableGroups(examId ?? 0, q),
    queryFn: () =>
      get<{ items: AssignableGroupItem[] }>(
        `v1/learning/admin/exams/${examId}/assignable-groups`,
        { searchParams: toSearchParams({ q }) },
      ),
    enabled: enabled && typeof examId === 'number',
  })

export const useExamAssignableEmployees = (
  examId: number | null,
  params: { q?: string; page?: number; per_page?: number },
  enabled: boolean,
) =>
  useQuery({
    queryKey: learningExamKeys.assignableEmployees(examId ?? 0, params as Params),
    queryFn: () =>
      get<AssignableEmployeeListResponse>(
        `v1/learning/admin/exams/${examId}/assignable-employees`,
        { searchParams: toSearchParams(params as Params) },
      ),
    enabled: enabled && typeof examId === 'number',
  })

export const useExamResults = (
  examId: number | null | undefined,
  params?: { q?: string; page?: number; per_page?: number },
) =>
  useQuery({
    queryKey: learningExamKeys.results(examId ?? 0, (params ?? {}) as Params),
    queryFn: () =>
      get<ExamResultListResponse>(`v1/learning/admin/exams/${examId}/results`, {
        searchParams: toSearchParams(params as Params),
      }),
    enabled: typeof examId === 'number',
    placeholderData: (prev) => prev,
  })

// ---------------------------------------------------------------------------
// Employee side
// ---------------------------------------------------------------------------

export const useMyExams = (params?: { q?: string; page?: number; per_page?: number }) =>
  useQuery({
    queryKey: learningExamKeys.myExams((params ?? {}) as Params),
    queryFn: () =>
      get<MyExamListResponse>('v1/learning/my/exams', {
        searchParams: toSearchParams(params as Params),
      }),
    placeholderData: (prev) => prev,
  })

export const useMyExamSummary = (id: number | null | undefined) =>
  useQuery({
    queryKey: learningExamKeys.myExam(id),
    queryFn: () => get<MyExamSummary>(`v1/learning/my/exams/${id}`),
    enabled: typeof id === 'number',
  })

export const useStartExamAttempt = () =>
  useMutation({
    mutationFn: (examId: number) =>
      post<AttemptStartResponse>(`v1/learning/my/exams/${examId}/attempts`),
    retry: false,
  })

export const useExamAttempt = (attemptId: number | null | undefined) =>
  useQuery({
    queryKey: learningExamKeys.attempt(attemptId ?? 0),
    queryFn: () => get<AttemptDetailResponse>(`v1/learning/my/exam-attempts/${attemptId}`),
    enabled: typeof attemptId === 'number',
  })

export const useSubmitExamAttempt = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ attemptId, answers }: { attemptId: number; answers: Record<string, string[]> }) =>
      post<AttemptSubmitResponse>(`v1/learning/my/exam-attempts/${attemptId}/submit`, {
        json: { answers },
      }),
    retry: false,
    onSuccess: (_data, { attemptId }) => {
      queryClient.invalidateQueries({ queryKey: learningExamKeys.attempt(attemptId) })
      invalidateMyExamQueries(queryClient)
    },
  })
}

export const useAbandonExamAttempt = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (attemptId: number) =>
      post(`v1/learning/my/exam-attempts/${attemptId}/abandon`),
    retry: false,
    onSuccess: () => invalidateMyExamQueries(queryClient),
  })
}
