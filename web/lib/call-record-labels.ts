/** Display labels for target call-record summaries and WebRTC device errors. */

import { t } from '@/utils/i18n'

const CALL_RECORD_STATE_ZH: Record<string, string> = {
  active: '进行中',
  ended: '已结束',
}

const CALL_RESULT_ZH: Record<string, string> = {
  agent_answered: '客服接听',
  bot_completed: '机器人完成',
  customer_abandoned: '客户放弃',
  no_agent_available: '无客服可用',
  no_answer: '无人接听',
  busy: '忙线',
  rejected: '已拒接',
  failed: '失败',
}

export function formatCallResult(result: string | null | undefined, isZh = true): string {
  if (!result) return ''
  if (!isZh) return result
  return CALL_RESULT_ZH[result] ?? result
}

export function formatCallRecordState(state: string | null | undefined, isZh = true): string {
  if (!state) return isZh ? '—' : '—'
  if (!isZh) return state
  return CALL_RECORD_STATE_ZH[state] ?? state
}

const HANGUP_REASON_ZH: Record<string, string> = {
  no_answer: '无人接听',
  no_agent_online: '无坐席在线',
  rejected: '坐席拒接',
  caller_hangup: '访客挂断',
  remote_bye: '访客挂断',
  agent_cancel: '坐席取消',
  local_cancel: '坐席取消',
  busy: '忙线',
  bridge_peer_gone: '对端断线',
  drain_timeout: '排队超时',
  manual_reset: '人工重置',
  reconnect_reconcile: '重连校正',
  supervisor_force_hangup: '班长挂断',
}

/** Map a stable CDR hangup reason code to an agent-facing label. */
export function formatHangupReason(reason: string | null | undefined, isZh = true): string {
  const raw = (reason ?? '').trim()
  if (!raw) return ''
  const locale = isZh ? 'zh' : 'en'
  const key = `ws.records.calls.option.hangupReason.${raw}`
  const translated = t(key, locale)
  if (translated !== key) return translated
  if (!isZh) return raw
  if (raw.startsWith('voicespeed')) return '机器人结束'
  return HANGUP_REASON_ZH[raw] ?? raw
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
