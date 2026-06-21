'use client'

import { useEffect } from 'react'
import {
  bindWorkspaceNotificationAlertUnlock,
  playWorkspaceMessageAlert,
  playWorkspaceSessionAlert,
} from '@/lib/workspace-notification-alert'

export function useWorkspaceNotificationAlert() {
  useEffect(() => bindWorkspaceNotificationAlertUnlock(), [])

  return {
    playMessageAlert: playWorkspaceMessageAlert,
    playSessionAlert: playWorkspaceSessionAlert,
  }
}
