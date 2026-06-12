import { useMutation, useQuery } from '@tanstack/react-query'
import { get, post } from '@/service/base'
import type { LoginPayload, LoginResponse, UserInfo } from '@/models/auth'

export const authKeys = {
  currentUser: ['auth', 'me'] as const,
}

export const useLogin = () =>
  useMutation({
    mutationFn: (data: LoginPayload) =>
      post<LoginResponse>('v1/auth/login', { json: data }),
  })

export const useCurrentUser = (enabled = true) =>
  useQuery({
    queryKey: authKeys.currentUser,
    queryFn: () => get<UserInfo>('v1/auth/me'),
    enabled,
    staleTime: 0,
  })
