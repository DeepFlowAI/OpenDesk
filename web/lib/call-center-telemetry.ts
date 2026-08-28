'use client'

import type { TelemetryLevel } from '@/models/telemetry'
import { telemetry } from '@/service/telemetry'

type TrackableProps = Record<string, string | number | boolean | null | undefined>

/**
 * Desk telemetry for the call-center runtime.
 *
 * A stuck desk (still showing 外呼中 after the customer answered, a hangup
 * that appears to do nothing, a refresh that changes nothing) is hard to
 * reproduce on demand, so the runtime reports every socket event it receives,
 * every phase change, and every time a poll had to reconcile state the socket
 * should have delivered. Together those make the failure diagnosable from
 * logs alone.
 */
export function trackCallCenter(
  name: string,
  props: TrackableProps,
  level: TelemetryLevel = 'info',
): void {
  const cleaned: Record<string, string | number | boolean> = {}
  for (const [key, value] of Object.entries(props)) {
    if (value != null) cleaned[key] = value
  }
  telemetry.trackApp(`cc_${name}`, { level, props: cleaned })
}
