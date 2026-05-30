import { useQuery } from '@tanstack/react-query'
import { get } from './base'
import type { SystemVariable } from '@/models/voice-flow'

export const useSystemVariables = () =>
  useQuery({
    queryKey: ['voice-flows', 'system-variables'],
    queryFn: () => get<{ items: SystemVariable[] }>('v1/voice-flows/system-variables'),
    staleTime: Infinity,
  })
