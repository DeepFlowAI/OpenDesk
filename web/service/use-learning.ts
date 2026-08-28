import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, postForm, put } from './base'
import type {
  AdminCourseListResponse,
  AssignableEmployeeListResponse,
  AssignableGroupItem,
  AssignmentItem,
  CompleteMaterialResponse,
  CourseStatus,
  CourseVisibility,
  LearnerListResponse,
  LearningCourse,
  LearningCourseDetail,
  LearningMaterial,
  LearningMaterialCreatePayload,
  LearningRecord,
  MaterialOpenResponse,
  MaterialUploadCredentialRequest,
  MaterialUploadCredentialResponse,
  MyCourseDetail,
  MyCourseListResponse,
  AssignmentTargetType,
} from '@/models/learning'

const NS = 'learning'

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

export const learningKeys = {
  all: [NS] as const,
  adminCourses: (params: Params) => [...learningKeys.all, 'admin-courses', params] as const,
  course: (id: number | null | undefined) => [...learningKeys.all, 'course', id] as const,
  assignments: (courseId: number) => [...learningKeys.all, 'assignments', courseId] as const,
  assignableGroups: (courseId: number, q?: string) =>
    [...learningKeys.all, 'assignable-groups', courseId, q ?? ''] as const,
  assignableEmployees: (courseId: number, params: Params) =>
    [...learningKeys.all, 'assignable-employees', courseId, params] as const,
  learners: (courseId: number, params: Params) =>
    [...learningKeys.all, 'learners', courseId, params] as const,
  myCourses: (params: Params) => [...learningKeys.all, 'my-courses', params] as const,
  myCourse: (id: number | null | undefined) => [...learningKeys.all, 'my-course', id] as const,
}

function useInvalidateCourse() {
  const queryClient = useQueryClient()
  return (courseId: number) => invalidateCourseQueries(queryClient, courseId)
}

function invalidateCourseQueries(queryClient: ReturnType<typeof useQueryClient>, courseId: number) {
  queryClient.invalidateQueries({ queryKey: learningKeys.course(courseId) })
  queryClient.invalidateQueries({ queryKey: [NS, 'admin-courses'] })
  queryClient.invalidateQueries({ queryKey: learningKeys.assignments(courseId) })
  queryClient.invalidateQueries({ queryKey: [NS, 'learners', courseId] })
  queryClient.invalidateQueries({ queryKey: [NS, 'assignable-groups', courseId] })
  queryClient.invalidateQueries({ queryKey: [NS, 'assignable-employees', courseId] })
}

// ---------------------------------------------------------------------------
// Admin: courses
// ---------------------------------------------------------------------------

export interface AdminCourseListParams {
  page?: number
  per_page?: number
  q?: string
  status?: CourseStatus | ''
}

export const useAdminCourses = (params?: AdminCourseListParams) =>
  useQuery({
    queryKey: learningKeys.adminCourses((params ?? {}) as Params),
    queryFn: () =>
      get<AdminCourseListResponse>('v1/learning/admin/courses', {
        searchParams: toSearchParams(params as Params),
      }),
    placeholderData: (prev) => prev,
  })

export const useAdminCourse = (id: number | null | undefined) =>
  useQuery({
    queryKey: learningKeys.course(id),
    queryFn: () => get<LearningCourseDetail>(`v1/learning/admin/courses/${id}`),
    enabled: typeof id === 'number',
  })

export const useCreateCourse = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name?: string }) =>
      post<LearningCourse>('v1/learning/admin/courses', { json: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [NS, 'admin-courses'] }),
  })
}

export const useUpdateCourse = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (payload: { name?: string; intro?: string; cover_url?: string }) =>
      put<LearningCourse>(`v1/learning/admin/courses/${courseId}`, { json: payload }),
    onSuccess: () => invalidate(courseId),
  })
}

export const usePublishCourse = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: number) =>
      post<LearningCourse>(`v1/learning/admin/courses/${courseId}/publish`),
    onSuccess: (_data, courseId) => invalidateCourseQueries(queryClient, courseId),
  })
}

export const useUnpublishCourse = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: number) =>
      post<LearningCourse>(`v1/learning/admin/courses/${courseId}/unpublish`),
    onSuccess: (_data, courseId) => invalidateCourseQueries(queryClient, courseId),
  })
}

export const useDeleteCourse = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: number) => del(`v1/learning/admin/courses/${courseId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [NS, 'admin-courses'] }),
  })
}

export const useUploadCourseCover = () =>
  useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return postForm<{ url: string }>('v1/learning/admin/courses/cover', formData)
    },
  })

// ---------------------------------------------------------------------------
// Admin: sections
// ---------------------------------------------------------------------------

export const useCreateSection = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (name?: string) =>
      post<import('@/models/learning').LearningSection>(
        `v1/learning/admin/courses/${courseId}/sections`,
        { json: { name: name ?? null } },
      ),
    onSuccess: () => invalidate(courseId),
  })
}

export const useRenameSection = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: ({ sectionId, name }: { sectionId: number; name: string }) =>
      put<import('@/models/learning').LearningSection>(`v1/learning/admin/sections/${sectionId}`, {
        json: { name },
      }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useReorderSections = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (orderedIds: number[]) =>
      put(`v1/learning/admin/courses/${courseId}/sections/order`, {
        json: { ordered_ids: orderedIds },
      }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useDeleteSection = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (sectionId: number) => del(`v1/learning/admin/sections/${sectionId}`),
    onSuccess: () => invalidate(courseId),
  })
}

// ---------------------------------------------------------------------------
// Admin: materials
// ---------------------------------------------------------------------------

export const useUploadCredential = () =>
  useMutation({
    mutationFn: (payload: MaterialUploadCredentialRequest) =>
      post<MaterialUploadCredentialResponse>('v1/learning/admin/materials/upload-credential', {
        json: payload,
      }),
    retry: false,
  })

export const useCreateMaterial = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: ({ sectionId, payload }: { sectionId: number; payload: LearningMaterialCreatePayload }) =>
      post<LearningMaterial>(`v1/learning/admin/sections/${sectionId}/materials`, { json: payload }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useRenameMaterial = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: ({ materialId, name }: { materialId: number; name: string }) =>
      put<LearningMaterial>(`v1/learning/admin/materials/${materialId}`, { json: { name } }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useReorderMaterials = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: ({ sectionId, orderedIds }: { sectionId: number; orderedIds: number[] }) =>
      put(`v1/learning/admin/sections/${sectionId}/materials/order`, {
        json: { ordered_ids: orderedIds },
      }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useDeleteMaterial = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (materialId: number) => del(`v1/learning/admin/materials/${materialId}`),
    onSuccess: () => invalidate(courseId),
  })
}

export const useRetranscodeMaterial = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (materialId: number) =>
      post<LearningMaterial>(`v1/learning/admin/materials/${materialId}/retranscode`),
    onSuccess: () => invalidate(courseId),
  })
}

// ---------------------------------------------------------------------------
// Admin: visibility & assignments & learners
// ---------------------------------------------------------------------------

export const useUpdateVisibility = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (visibility: CourseVisibility) =>
      put<LearningCourse>(`v1/learning/admin/courses/${courseId}/visibility`, {
        json: { visibility },
      }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useAssignments = (courseId: number | null | undefined) =>
  useQuery({
    queryKey: learningKeys.assignments(courseId ?? 0),
    queryFn: () =>
      get<{ items: AssignmentItem[] }>(`v1/learning/admin/courses/${courseId}/assignments`),
    enabled: typeof courseId === 'number',
  })

export const useAddAssignments = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (targets: { target_type: AssignmentTargetType; target_id: number }[]) =>
      post<{ added_count: number }>(`v1/learning/admin/courses/${courseId}/assignments`, {
        json: { targets },
      }),
    onSuccess: () => invalidate(courseId),
  })
}

export const useRemoveAssignment = (courseId: number) => {
  const invalidate = useInvalidateCourse()
  return useMutation({
    mutationFn: (assignmentId: number) =>
      del(`v1/learning/admin/courses/${courseId}/assignments/${assignmentId}`),
    onSuccess: () => invalidate(courseId),
  })
}

export const useAssignableGroups = (courseId: number | null, q: string, enabled: boolean) =>
  useQuery({
    queryKey: learningKeys.assignableGroups(courseId ?? 0, q),
    queryFn: () =>
      get<{ items: AssignableGroupItem[] }>(
        `v1/learning/admin/courses/${courseId}/assignable-groups`,
        { searchParams: toSearchParams({ q }) },
      ),
    enabled: enabled && typeof courseId === 'number',
  })

export const useAssignableEmployees = (
  courseId: number | null,
  params: { q?: string; page?: number; per_page?: number },
  enabled: boolean,
) =>
  useQuery({
    queryKey: learningKeys.assignableEmployees(courseId ?? 0, params as Params),
    queryFn: () =>
      get<AssignableEmployeeListResponse>(
        `v1/learning/admin/courses/${courseId}/assignable-employees`,
        { searchParams: toSearchParams(params as Params) },
      ),
    enabled: enabled && typeof courseId === 'number',
  })

export const useLearners = (
  courseId: number | null | undefined,
  params?: { q?: string; page?: number; per_page?: number },
) =>
  useQuery({
    queryKey: learningKeys.learners(courseId ?? 0, (params ?? {}) as Params),
    queryFn: () =>
      get<LearnerListResponse>(`v1/learning/admin/courses/${courseId}/learners`, {
        searchParams: toSearchParams(params as Params),
      }),
    enabled: typeof courseId === 'number',
    placeholderData: (prev) => prev,
  })

// ---------------------------------------------------------------------------
// Employee side
// ---------------------------------------------------------------------------

export const useMyCourses = (params?: { q?: string; page?: number; per_page?: number }) =>
  useQuery({
    queryKey: learningKeys.myCourses((params ?? {}) as Params),
    queryFn: () =>
      get<MyCourseListResponse>('v1/learning/my/courses', {
        searchParams: toSearchParams(params as Params),
      }),
    placeholderData: (prev) => prev,
  })

export const useMyCourseDetail = (id: number | null | undefined) =>
  useQuery({
    queryKey: learningKeys.myCourse(id),
    queryFn: () => get<MyCourseDetail>(`v1/learning/my/courses/${id}`),
    enabled: typeof id === 'number',
  })

export const useOpenMaterial = () =>
  useMutation({
    mutationFn: (materialId: number) =>
      post<MaterialOpenResponse>(`v1/learning/my/materials/${materialId}/open`),
    retry: false,
  })

export const useReportProgress = () =>
  useMutation({
    mutationFn: ({ materialId, positionSeconds }: { materialId: number; positionSeconds: number }) =>
      put<LearningRecord>(`v1/learning/my/materials/${materialId}/progress`, {
        json: { position_seconds: positionSeconds },
      }),
    retry: false,
  })

export const useCompleteMaterial = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (materialId: number) =>
      post<CompleteMaterialResponse>(`v1/learning/my/materials/${materialId}/complete`),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [NS, 'my-courses'] })
      queryClient.invalidateQueries({ queryKey: [NS, 'my-course'] })
    },
  })
}
