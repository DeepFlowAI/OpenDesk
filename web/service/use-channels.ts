import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type { Channel, CreateChannelPayload, UpdateChannelPayload } from '@/models/channel'

const NS = 'channels'

export const channelKeys = {
  all: [NS] as const,
  lists: () => [...channelKeys.all, 'list'] as const,
  details: () => [...channelKeys.all, 'detail'] as const,
  detail: (id: number) => [...channelKeys.details(), id] as const,
}

export const useChannels = () =>
  useQuery({
    queryKey: channelKeys.lists(),
    queryFn: () => get<Channel[]>('v1/channels'),
  })

export const useChannel = (id: number) =>
  useQuery({
    queryKey: channelKeys.detail(id),
    queryFn: () => get<Channel>(`v1/channels/${id}`),
    enabled: !!id,
  })

export const useCreateChannel = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateChannelPayload) =>
      post<Channel>('v1/channels', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: channelKeys.lists() }),
  })
}

export const useUpdateChannel = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateChannelPayload }) =>
      put<Channel>(`v1/channels/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: channelKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: channelKeys.lists() })
    },
  })
}

export const useDeleteChannel = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/channels/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: channelKeys.lists() }),
  })
}

export const useCopyChannel = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Channel>(`v1/channels/${id}/copy`),
    onSuccess: (channel) => {
      qc.invalidateQueries({ queryKey: channelKeys.detail(channel.id) })
      qc.invalidateQueries({ queryKey: channelKeys.lists() })
    },
  })
}

export const useRotateChannelKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Channel>(`v1/channels/${id}/rotate-key`),
    onSuccess: (channel) => {
      qc.invalidateQueries({ queryKey: channelKeys.detail(channel.id) })
      qc.invalidateQueries({ queryKey: channelKeys.lists() })
    },
  })
}
