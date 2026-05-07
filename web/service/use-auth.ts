import { useMutation } from '@tanstack/react-query'
import { post } from '@/service/base'
import type { LoginPayload, LoginResponse } from '@/models/auth'

export const useLogin = () =>
  useMutation({
    mutationFn: (data: LoginPayload) =>
      post<LoginResponse>('v1/auth/login', { json: data }),
  })
