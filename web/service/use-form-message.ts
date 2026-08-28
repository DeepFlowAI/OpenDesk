import { useMutation, useQuery } from '@tanstack/react-query'
import ky from 'ky'

import type {
  PublicFormMessageConfigResponse,
  PublicFormMessageSubmitPayload,
  PublicFormMessageSubmitResponse,
} from '@/models/form-message'
import type { FieldFileAttachment } from '@/app/components/features/field-system/field-file-editor'

const publicClient = ky.create({
  prefixUrl: process.env.NEXT_PUBLIC_API_URL ?? '',
  timeout: 30000,
})

const visitorHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

export const usePublicFormMessageConfig = (visitorSessionToken: string, enabled: boolean) =>
  useQuery({
    queryKey: ['public', 'form-message', visitorSessionToken],
    queryFn: () => publicClient.get('v1/public/form-messages/config', {
      headers: visitorHeaders(visitorSessionToken),
    }).json<PublicFormMessageConfigResponse>(),
    enabled: enabled && !!visitorSessionToken,
    staleTime: Infinity,
    retry: 1,
  })

export const useSubmitPublicFormMessage = (visitorSessionToken: string) =>
  useMutation({
    mutationFn: (payload: PublicFormMessageSubmitPayload) =>
      publicClient.post('v1/public/form-messages/submit', {
        headers: visitorHeaders(visitorSessionToken),
        json: payload,
      }).json<PublicFormMessageSubmitResponse>(),
  })

export const useUploadPublicFormMessageFile = (visitorSessionToken: string) =>
  useMutation({
    mutationFn: ({ file, version, fieldRef }: { file: File; version: number; fieldRef: string }) => {
      const body = new FormData()
      body.append('file', file)
      body.append('version', String(version))
      body.append('field_ref', fieldRef)
      return publicClient.post('v1/public/form-messages/files', {
        headers: visitorHeaders(visitorSessionToken),
        body,
      }).json<FieldFileAttachment>()
    },
  })
