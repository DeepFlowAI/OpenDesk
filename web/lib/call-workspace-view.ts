/**
 * Which main pane the call workspace should show for a live session.
 *
 * The top call bar is independent of this. Task / personal-auto workbenches
 * keep their own records and scripts; only inbound and ad-hoc dials jump to
 * the regular screen-pop.
 */

export type CallWorkspaceMainView = 'outbound-tasks' | 'personal-auto-outbound' | 'screen-pop'

export type CallWorkspaceAnchor = {
  view: 'outbound-tasks' | 'personal-auto-outbound'
  phone?: string
  callId?: string
  taskId?: number
} | null

export type CallWorkspaceRouteEvent =
  | { type: 'task-call-armed'; phone: string; taskId?: number }
  | { type: 'dial-started'; destination: string; callId: string }
  | { type: 'incoming'; source?: string | null; callId?: string | null }
  | { type: 'select-recent'; isCurrentLive: boolean }

export function normalizeDialPhone(value: string | undefined | null): string {
  return (value ?? '').replace(/\s+/g, '').trim()
}

export function isTaskDialDestination(anchor: CallWorkspaceAnchor, destination: string): boolean {
  return (
    anchor?.view === 'outbound-tasks' &&
    Boolean(anchor.phone) &&
    normalizeDialPhone(anchor.phone) === normalizeDialPhone(destination)
  )
}

export function nextAnchorAfterDialNumberChange(
  anchor: CallWorkspaceAnchor,
  nextNumber: string,
): CallWorkspaceAnchor {
  if (anchor?.view !== 'outbound-tasks' || anchor.callId) return anchor
  if (!anchor.phone) return anchor
  if (normalizeDialPhone(nextNumber) === normalizeDialPhone(anchor.phone)) return anchor
  return null
}

/** Drop a bound live-call lock when the session returns to idle; keep a pending fill. */
export function nextAnchorAfterIdle(anchor: CallWorkspaceAnchor): CallWorkspaceAnchor {
  if (anchor && !anchor.callId) return anchor
  return null
}

export function taskDialBlockReason(input: {
  phase: string
  canDialOutbound: boolean
  hasUsableDevice: boolean
  micChecking: boolean
  outboundNumberId: string
  agentStatus?: string
}): string | null {
  if (!input.canDialOutbound) return '没有外呼权限'
  if (input.phase !== 'idle') return '当前无法发起外呼'
  if (input.micChecking || !input.hasUsableDevice) return '请先选择可用呼叫设备'
  if (input.agentStatus === 'offline') return '请先将客服状态切换为就绪'
  if (!input.outboundNumberId.trim()) return '请先选择外呼号码'
  return null
}

export function callWorkspaceHref(view: CallWorkspaceMainView, anchor?: CallWorkspaceAnchor): string {
  if (view === 'outbound-tasks') {
    const taskId = anchor?.view === 'outbound-tasks' ? anchor.taskId : undefined
    return taskId
      ? `/workspace/call?view=outbound-tasks&taskId=${taskId}`
      : '/workspace/call?view=outbound-tasks'
  }
  if (view === 'personal-auto-outbound') return '/workspace/call?view=personal-auto-outbound'
  return '/workspace/call'
}

export function resolveCallWorkspaceRoute(input: {
  currentView: CallWorkspaceMainView
  anchor: CallWorkspaceAnchor
  event: CallWorkspaceRouteEvent
}): { view: CallWorkspaceMainView; anchor: CallWorkspaceAnchor } {
  const { currentView, anchor, event } = input

  switch (event.type) {
    case 'task-call-armed':
      return {
        view: 'outbound-tasks',
        anchor: { view: 'outbound-tasks', phone: event.phone, taskId: event.taskId },
      }

    case 'dial-started': {
      if (isTaskDialDestination(anchor, event.destination)) {
        return {
          view: 'outbound-tasks',
          anchor: {
            view: 'outbound-tasks',
            phone: anchor?.phone,
            callId: event.callId,
            taskId: anchor?.taskId,
          },
        }
      }
      return { view: 'screen-pop', anchor: null }
    }

    case 'incoming': {
      if (event.source === 'personal_auto_outbound') {
        return {
          view: currentView,
          anchor: {
            view: 'personal-auto-outbound',
            callId: event.callId ?? undefined,
          },
        }
      }
      return { view: 'screen-pop', anchor: null }
    }

    case 'select-recent': {
      if (event.isCurrentLive && anchor?.view) {
        return { view: anchor.view, anchor }
      }
      return { view: 'screen-pop', anchor }
    }
  }
}
