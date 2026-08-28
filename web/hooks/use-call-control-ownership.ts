'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import type { EmbeddedControlLease } from '@/models/embedded-call'
import { updateEmbeddedControl } from '@/service/use-embedded-call'
import { readStoredToken } from '@/utils/auth-session'


const INSTANCE_KEY = 'opendesk:call-control-instance'
const CONTROL_REFRESH_INTERVAL_MS = 5000
const EMBEDDED_SURFACE = 'embedded_call'

function embedOwnsLease(lease: EmbeddedControlLease | null, instanceId: string): boolean {
  return (
    lease?.is_owner === false &&
    lease.owner_surface === EMBEDDED_SURFACE &&
    Boolean(lease.owner_instance_id) &&
    lease.owner_instance_id !== instanceId
  )
}

function createInstanceId(): string {
  const bytes = new Uint8Array(12)
  crypto.getRandomValues(bytes)
  return `workspace_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`
}

export function useCallControlOwnership(enabled: boolean) {
  const [instanceId, setInstanceId] = useState('')
  const [lease, setLease] = useState<EmbeddedControlLease | null>(null)
  const leaseRef = useRef<EmbeddedControlLease | null>(null)
  leaseRef.current = lease

  useEffect(() => {
    if (!enabled) return
    let value = sessionStorage.getItem(INSTANCE_KEY)
    if (!value) {
      value = createInstanceId()
      sessionStorage.setItem(INSTANCE_KEY, value)
    }
    setInstanceId(value)
  }, [enabled])

  useEffect(() => {
    if (!enabled || !instanceId) return
    let cancelled = false
    let acquiring = false
    const acquire = async () => {
      if (acquiring || leaseRef.current?.is_owner) return
      acquiring = true
      try {
        const result = await updateEmbeddedControl('acquire', {
          instanceId,
          surface: 'opendesk_workspace',
        })
        if (!cancelled) setLease(result)
      } catch {
        if (!cancelled) setLease(null)
      } finally {
        acquiring = false
      }
    }
    void acquire()
    const timer = window.setInterval(() => void acquire(), CONTROL_REFRESH_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [enabled, instanceId])

  useEffect(() => {
    if (!enabled || !instanceId || !lease?.lease_token) return
    const timer = window.setInterval(() => {
      const token = leaseRef.current?.lease_token
      if (!token) return
      void updateEmbeddedControl('heartbeat', {
        instanceId,
        surface: 'opendesk_workspace',
        leaseToken: token,
      }).then(setLease).catch(() => setLease(null))
    }, CONTROL_REFRESH_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [enabled, instanceId, lease?.lease_token])

  useEffect(() => () => {
    const token = leaseRef.current?.lease_token
    if (!token || !instanceId) return
    // Logout / session expiry already cleared the token. The short lease
    // expires on its own; do not fire a guaranteed 401 on the login page.
    if (!readStoredToken()) return
    void updateEmbeddedControl('release', {
      instanceId,
      surface: 'opendesk_workspace',
      leaseToken: token,
    }).catch(() => {
      // Page is unloading or the session is already gone.
    })
  }, [instanceId])

  const takeover = useCallback(async () => {
    if (!instanceId) return
    const result = await updateEmbeddedControl('takeover', {
      instanceId,
      surface: 'opendesk_workspace',
    })
    setLease(result)
  }, [instanceId])

  const blockedByEmbed = enabled && embedOwnsLease(lease, instanceId)
  return {
    lease,
    isOwner: !blockedByEmbed,
    hasControlConflict: blockedByEmbed,
    takeover,
  }
}
