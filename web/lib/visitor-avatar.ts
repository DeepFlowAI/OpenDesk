import type { VisitorWebStatus } from '@/models/conversation'

export type VisitorAvatarState = VisitorWebStatus

export function visitorAvatarInitial(name?: string | null): string {
  const value = name?.trim() || '访'
  const character = Array.from(value)[0] || '访'
  return /[a-z]/i.test(character) ? character.toUpperCase() : character
}

export function resolveVisitorAvatarState(input: {
  status?: VisitorWebStatus
  canDisplay?: boolean
  enabled: boolean
  isError?: boolean
}): VisitorAvatarState {
  if (!input.enabled || input.canDisplay === false || input.isError) return 'unknown'
  if (input.status === 'online' || input.status === 'offline') return input.status
  return 'unknown'
}
