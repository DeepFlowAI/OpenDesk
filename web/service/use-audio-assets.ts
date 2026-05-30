import { useMutation, useQuery } from '@tanstack/react-query'
import { get, postForm, del } from './base'
import type { AudioAsset } from '@/models/voice-flow'

export const useUploadAudioAsset = () =>
  useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return postForm<AudioAsset>('v1/voice-flows/audio-assets', form)
    },
  })

export const useAudioAsset = (assetId: number | null) =>
  useQuery({
    queryKey: ['voice-flows', 'audio-assets', assetId],
    queryFn: () => get<AudioAsset>(`v1/voice-flows/audio-assets/${assetId}`),
    enabled: assetId != null,
  })

export const useDeleteAudioAsset = () =>
  useMutation({
    mutationFn: (id: number) => del(`v1/voice-flows/audio-assets/${id}`),
  })
