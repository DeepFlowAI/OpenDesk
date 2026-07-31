/** Display labels for call-record state / common WebRTC device errors. */

const CALL_RECORD_STATE_ZH: Record<string, string> = {
  ringing: '振铃中',
  queued: '排队中',
  in_progress: '通话中',
  completed: '已完成',
  missed: '未接听',
  abandoned: '已放弃',
  failed: '失败',
  rejected: '已拒接',
  no_answer: '无人接听',
  cancelled: '已取消',
  canceled: '已取消',
  busy: '忙线',
}

export function formatCallRecordState(state: string | null | undefined, isZh = true): string {
  if (!state) return isZh ? '—' : '—'
  if (!isZh) return state
  return CALL_RECORD_STATE_ZH[state] ?? state
}

/** Map raw browser / WebRTC errors to agent-facing Chinese copy. */
export function formatWebRtcDeviceError(raw: string | null | undefined): string {
  const msg = (raw ?? '').trim()
  if (!msg) return '通话设备不可用，请检查麦克风权限后重试'
  const lower = msg.toLowerCase()
  if (
    lower.includes('requested device not found') ||
    lower.includes('notfounderror') ||
    lower.includes('device not found')
  ) {
    return '未找到可用麦克风/耳机，请检查设备连接与浏览器权限后重试'
  }
  if (lower.includes('notallowederror') || lower.includes('permission denied')) {
    return '浏览器未授权麦克风，请在地址栏允许麦克风权限后重试'
  }
  if (lower.includes('notreadableerror') || lower.includes('could not start audio source')) {
    return '麦克风被其他应用占用，请关闭占用后重试'
  }
  return msg
}
