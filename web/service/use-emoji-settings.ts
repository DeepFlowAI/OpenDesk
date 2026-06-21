import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ky from 'ky'
import { get, put } from './base'
import type {
  EmojiSettingConfig,
  EmojiTargetConfig,
  SaveEmojiSettingsPayload,
} from '@/models/emoji-setting'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })

const NS = 'emoji-settings'

export const emojiSettingsKeys = {
  all: [NS] as const,
  current: () => [...emojiSettingsKeys.all, 'current'] as const,
  agent: () => [...emojiSettingsKeys.all, 'agent'] as const,
  publicUser: () => [...emojiSettingsKeys.all, 'public-user'] as const,
}

export const useEmojiSettings = (enabled = true) =>
  useQuery({
    queryKey: emojiSettingsKeys.current(),
    queryFn: () => get<EmojiSettingConfig>('v1/conversation-settings/emojis'),
    enabled,
    retry: false,
  })

export const useSaveEmojiSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: SaveEmojiSettingsPayload) =>
      put<EmojiSettingConfig>('v1/conversation-settings/emojis', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: emojiSettingsKeys.current() })
      qc.invalidateQueries({ queryKey: emojiSettingsKeys.agent() })
      qc.invalidateQueries({ queryKey: emojiSettingsKeys.publicUser() })
    },
  })
}

export const useAgentEmojiSettings = (enabled = true) =>
  useQuery({
    queryKey: emojiSettingsKeys.agent(),
    queryFn: () => get<EmojiTargetConfig>('v1/conversation-settings/emojis/agent'),
    enabled,
    retry: false,
  })

export const usePublicEmojiSettings = () =>
  useQuery({
    queryKey: emojiSettingsKeys.publicUser(),
    queryFn: () => publicClient.get('v1/public/emojis').json<EmojiTargetConfig>(),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })
