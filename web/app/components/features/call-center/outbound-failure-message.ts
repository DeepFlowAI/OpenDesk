/**
 * Map outbound hangup reason + SIP status to a friendly toast.
 *
 * Known reasons return short Chinese descriptions. Expected non-error reasons
 * (agent_cancel / remote_bye) return null. Unknown reasons surface raw values.
 */

export type OutboundFailureInput = {
  reason?: string | null
  sip_status?: number | null
}

export type OutboundFailureMessage = {
  /** Toast body. null = expected outcome, do not toast. */
  message: string | null
  /** Toast severity. 'info' for normal-end states like remote_bye, 'error'
   *  for actual failures the agent should see prominently. */
  level: 'error' | 'info'
  /** True when the reason was not in the known set — the message embeds the
   *  raw reason so users can report it back. */
  isFallback: boolean
}

const SIP_STATUS_HINTS: Record<number, string> = {
  408: '振铃超时',
  410: '该号码已失效',
  480: '对方暂时无法接通',
  486: '对方占线',
  403: '该号码无权外呼',
  404: '该号码无法路由',
  603: '对方拒接',
  600: '对方占线',
}

export function mapOutboundFailure(
  input: OutboundFailureInput,
): OutboundFailureMessage {
  const reason = (input.reason ?? '').trim()
  const sip = input.sip_status ?? null

  // ── Expected non-errors ──
  // agent_cancel: silent — the agent just clicked the cancel button.
  // remote_bye: friendly notice — the callee hung up after talking; we
  // still want a brief toast so the agent isn't left wondering whether
  // the call actually ended or audio dropped.
  if (reason === 'agent_cancel') {
    return { message: null, level: 'info', isFallback: false }
  }
  if (reason === 'remote_bye') {
    return { message: '对方已挂断', level: 'info', isFallback: false }
  }

  // ── Known failures — friendly text, possibly refined by sip_status ──
  if (reason === 'busy') {
    return { message: '对方占线，请稍后重试', level: 'error', isFallback: false }
  }
  if (reason === 'local_cancel') {
    // 487 with no user action = our 32s ring timeout. agent_cancel is
    // already handled above, so anything reaching here is the timeout.
    return { message: '振铃超时，对方未接听', level: 'error', isFallback: false }
  }
  if (reason === 'no_answer') {
    if (sip && SIP_STATUS_HINTS[sip]) {
      return { message: SIP_STATUS_HINTS[sip], level: 'error', isFallback: false }
    }
    return { message: '对方未接听', level: 'error', isFallback: false }
  }
  if (reason === 'rejected') {
    if (sip && SIP_STATUS_HINTS[sip]) {
      return { message: SIP_STATUS_HINTS[sip], level: 'error', isFallback: false }
    }
    return { message: '通话被拒绝', level: 'error', isFallback: false }
  }
  if (reason === 'originate_failed') {
    return { message: '系统繁忙，请稍后重试', level: 'error', isFallback: false }
  }
  if (reason === 'media_eof') {
    return { message: '媒体连接中断', level: 'error', isFallback: false }
  }
  if (reason === 'max_duration') {
    return { message: '通话超过最大时长，已自动挂断', level: 'error', isFallback: false }
  }
  if (reason === 'at_capacity') {
    return { message: '通话量已达上限，请稍后重试', level: 'error', isFallback: false }
  }
  if (reason === 'server_stopping') {
    return { message: '通话服务正在重启，请稍后重试', level: 'error', isFallback: false }
  }
  if (reason === 'no_route') {
    return { message: '未匹配到通话路由规则', level: 'error', isFallback: false }
  }
  if (reason === 'no_flow_version') {
    return { message: '语音流程未发布版本', level: 'error', isFallback: false }
  }
  if (
    reason === 'bind_failed' ||
    reason === 'ringing_failed' ||
    reason === 'answer_failed' ||
    reason === 'alloc_failed' ||
    reason === 'invite_failed'
  ) {
    return { message: '语音信令异常，请稍后重试', level: 'error', isFallback: false }
  }

  // ── Unknown — surface raw so the user can paste it back for a new mapping ──
  const parts: string[] = []
  if (reason) parts.push(reason)
  if (sip) parts.push(`SIP ${sip}`)
  const raw = parts.length > 0 ? parts.join(' / ') : '未知原因'
  return {
    message: `通话异常（${raw}），请反馈给技术`,
    level: 'error',
    isFallback: true,
  }
}
