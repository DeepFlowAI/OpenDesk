'use client'

import { useQuery } from '@tanstack/react-query'
import type { TicketExportConfig, TicketExportSource } from '@/models/ticket-export'
import { useExportIdentity } from '@/service/use-export-tasks'
import { post } from '@/service/base'

export function useTicketExportConfig(source: TicketExportSource) {
  const identity = useExportIdentity()
  return useQuery({
    queryKey: ['ticket-export-config', identity, source],
    queryFn: async ({ signal }) => {
      const result = await post<{ prepared: string; signature: string; count: number }>('v1/tickets/export-config', {
        json: { query: source.query, language: source.language }, signal,
      })
      return { ...result, token: result.prepared, prepared: JSON.parse(result.prepared) as TicketExportConfig['prepared'] }
    },
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  })
}
