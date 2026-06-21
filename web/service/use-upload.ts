import { useMutation } from '@tanstack/react-query'
import { postForm } from './base'

export const useUploadAvatar = () => {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await postForm<{ url: string }>('v1/upload/avatar', formData)
      return resp.url
    },
  })
}

export const useUploadChannelBotAvatar = useUploadAvatar

export const useUploadChannelLogo = () => {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await postForm<{ url: string }>('v1/upload/channel-logo', formData)
      return resp.url
    },
  })
}

export const useUploadChannelFavicon = () => {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await postForm<{ url: string }>('v1/upload/channel-favicon', formData)
      return resp.url
    },
  })
}

export type CustomFieldFileUploadResult = {
  url: string
  name: string
  size: number
  content_type: string | null
}

/** Generic upload for custom field FILE type (JSON attachments). */
export const useUploadCustomFieldFile = () => {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return postForm<CustomFieldFileUploadResult>('v1/upload/custom-field-file', formData)
    },
  })
}
