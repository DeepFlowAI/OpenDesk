export type SendVerifyCodePayload = {
  tenant: string
  username: string
  locale: string
}

export type SendVerifyCodeResponse = {
  message: string
}

export type ResetPasswordPayload = {
  tenant: string
  username: string
  verify_code: string
  new_password: string
}

export type ResetPasswordResponse = {
  message: string
}
