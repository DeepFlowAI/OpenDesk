import { z } from 'zod'

const TENANT_REGEX = /^[a-zA-Z0-9-]{2,32}$/
const USERNAME_REGEX = /^[a-zA-Z0-9_]{4,32}$/
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const PASSWORD_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,32}$/
const VERIFY_CODE_REGEX = /^\d{6}$/

export const loginSchema = z.object({
  tenant: z
    .string()
    .min(1, 'validation.tenant.required')
    .regex(TENANT_REGEX, 'validation.tenant.format'),
  username: z
    .string()
    .min(1, 'validation.username.required')
    .refine(
      (val) => (val.includes('@') ? EMAIL_REGEX.test(val) : USERNAME_REGEX.test(val)),
      { message: 'validation.username.format' }
    ),
  password: z
    .string()
    .min(1, 'validation.password.required')
    .regex(PASSWORD_REGEX, 'validation.password.format'),
})

export type LoginFormData = z.infer<typeof loginSchema>

export const sendCodeSchema = z.object({
  tenant: z
    .string()
    .min(1, 'validation.tenant.required')
    .regex(TENANT_REGEX, 'validation.tenant.format'),
  username: z
    .string()
    .min(1, 'validation.username.required')
    .refine(
      (val) => (val.includes('@') ? EMAIL_REGEX.test(val) : USERNAME_REGEX.test(val)),
      { message: 'validation.username.format' }
    ),
})

export const forgotPasswordSchema = z
  .object({
    tenant: z
      .string()
      .min(1, 'validation.tenant.required')
      .regex(TENANT_REGEX, 'validation.tenant.format'),
    username: z
      .string()
      .min(1, 'validation.username.required')
      .refine(
        (val) => (val.includes('@') ? EMAIL_REGEX.test(val) : USERNAME_REGEX.test(val)),
        { message: 'validation.username.format' }
      ),
    verifyCode: z
      .string()
      .min(1, 'validation.verifyCode.required')
      .regex(VERIFY_CODE_REGEX, 'validation.verifyCode.format'),
    newPassword: z
      .string()
      .min(1, 'validation.newPassword.required')
      .regex(PASSWORD_REGEX, 'validation.newPassword.format'),
    confirmPassword: z.string().min(1, 'validation.confirmPassword.required'),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: 'validation.confirmPassword.mismatch',
    path: ['confirmPassword'],
  })

export type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>
