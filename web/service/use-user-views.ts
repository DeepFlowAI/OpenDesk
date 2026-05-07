import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  UserView,
  CreateUserViewPayload,
  UpdateUserViewPayload,
  UserViewSortPayload,
  UserViewTogglePayload,
} from '@/models/user-view'
import type { PaginatedResponse } from '@/models/common'

const NS = 'userViews'

export const userViewKeys = {
  all: [NS] as const,
  lists: () => [...userViewKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...userViewKeys.lists(), params] as const,
  details: () => [...userViewKeys.all, 'detail'] as const,
  detail: (id: number) => [...userViewKeys.details(), id] as const,
}

export const useUserViews = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: userViewKeys.list(params ?? {}),
    queryFn: () => get<PaginatedResponse<UserView>>('v1/user-views', { searchParams: params }),
  })

export const useUserView = (id: number) =>
  useQuery({
    queryKey: userViewKeys.detail(id),
    queryFn: () => get<UserView>(`v1/user-views/${id}`),
    enabled: !!id,
  })

export const useCreateUserView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateUserViewPayload) =>
      post<UserView>('v1/user-views', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: userViewKeys.lists() }),
  })
}

export const useUpdateUserView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateUserViewPayload }) =>
      put<UserView>(`v1/user-views/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: userViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: userViewKeys.lists() })
    },
  })
}

export const useDeleteUserView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/user-views/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: userViewKeys.lists() }),
  })
}

export const useToggleUserView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UserViewTogglePayload }) =>
      put<UserView>(`v1/user-views/${id}/toggle`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: userViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: userViewKeys.lists() })
    },
  })
}

export const useSortUserViews = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UserViewSortPayload) =>
      put<{ message: string }>('v1/user-views/sort', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: userViewKeys.lists() }),
  })
}
