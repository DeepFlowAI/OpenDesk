'use client'

import { useCallback } from 'react'

import { useAuthStore } from '@/context/auth-store'
import { workspaceCallOutboundNumberId } from '@/lib/call-outbound-number'
import type { UserPreferences } from '@/models/auth'
import { useUpdateCurrentUserPreferences } from '@/service/use-auth'

export function useWorkspaceCallOutboundPreference() {
  const preferredId = useAuthStore((state) =>
    workspaceCallOutboundNumberId(state.user?.preferences),
  )
  const updatePreferences = useUpdateCurrentUserPreferences()

  const savePreferredId = useCallback(
    (id: string) => {
      const current = useAuthStore.getState().user
      if (!current || workspaceCallOutboundNumberId(current.preferences) === id) return

      const preferences: UserPreferences = {
        ...current.preferences,
        workspace_call: {
          ...(current.preferences.workspace_call ?? {}),
          outbound_number_id: id,
        },
      }
      useAuthStore.getState().updateUser({ preferences })
      updatePreferences.mutate(preferences, {
        onSuccess: (nextUser) => useAuthStore.getState().setUser(nextUser),
      })
    },
    [updatePreferences],
  )

  return { preferredId, savePreferredId }
}
