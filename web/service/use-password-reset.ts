import { useMutation } from '@tanstack/react-query'
import { post } from '@/service/base'
import type {
  SendVerifyCodePayload,
  SendVerifyCodeResponse,
  ResetPasswordPayload,
  ResetPasswordResponse,
} from '@/models/password-reset'

export const useSendVerifyCode = () =>
  useMutation({
    mutationFn: (data: SendVerifyCodePayload) =>
      post<SendVerifyCodeResponse>('v1/auth/send-verify-code', { json: data }),
  })

export const useResetPassword = () =>
  useMutation({
    mutationFn: (data: ResetPasswordPayload) =>
      post<ResetPasswordResponse>('v1/auth/reset-password', { json: data }),
  })
