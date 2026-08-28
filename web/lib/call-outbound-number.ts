import type { UserPreferences } from '@/models/auth'

export function workspaceCallOutboundNumberId(
  preferences: UserPreferences | null | undefined,
): string | undefined {
  const value = preferences?.workspace_call?.outbound_number_id
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

export function resolvePreferredOutboundNumber<T extends { id: string }>(
  numbers: T[],
  preferredId?: string | null,
): T | undefined {
  if (numbers.length === 0) return undefined
  if (preferredId) {
    const preferred = numbers.find((item) => item.id === preferredId)
    if (preferred) return preferred
  }
  return numbers[0]
}
