/**
 * Map outbound hangup reason + SIP status to a friendly toast.
 *
 * Known reasons return short Chinese descriptions. Expected non-error reasons
 * (agent_cancel / agent_hangup / remote_bye) return null or an info toast.
 * A final SIP status always wins over a generic reason so 486/480/503/488
 * (and unlisted 4xx/5xx/6xx) never fall through to "请反馈给技术".
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

/** RFC 3261 / 3265 / 3311 / 3329 / 4032 / 4412 / 6086 + carrier extras. */
const SIP_STATUS_HINTS: Record<number, string> = {
  300: '呼叫被重定向',
  301: '被叫号码已永久迁移',
  302: '被叫号码已临时迁移',
  305: '需要经代理转发',
  380: '对方使用了替代服务',
  400: '呼叫请求无效',
  401: '线路鉴权失败',
  402: '线路余额不足',
  403: '该号码无权外呼',
  404: '该号码无法路由',
  405: '运营商不支持该呼叫',
  406: '运营商不接受该呼叫',
  407: '线路鉴权失败',
  408: '振铃超时',
  410: '该号码已失效',
  412: '条件请求失败',
  413: '呼叫请求过大',
  414: '呼叫地址过长',
  415: '媒体格式不受支持',
  416: '不支持该扩展',
  417: '未知资源优先级',
  420: '运营商扩展不被支持',
  421: '需要扩展才能完成呼叫',
  422: '会话间隔过短',
  423: '刷新间隔过短',
  428: '需要身份断言',
  429: '外呼过于频繁，请稍后重试',
  430: '流程失败',
  433: '对方不允许匿名呼叫',
  436: '身份信息错误',
  437: '身份信息不受支持',
  438: '身份信息无效',
  439: '首次跳转被禁止',
  440: '超出最大广度',
  469: '需要错误信息',
  470: '双方意见不一致',
  478: '无法解析被叫号码',
  479: '无法解析被叫号码',
  480: '对方暂时无法接通',
  481: '通话已不存在',
  482: '呼叫路由成环',
  483: '路由跳数过多',
  484: '号码不完整',
  485: '号码不明确',
  486: '对方占线',
  487: '呼叫已取消',
  488: '媒体协商失败',
  489: '事件包不受支持',
  491: '对方正在处理另一路呼叫',
  493: '无法解密呼叫',
  494: '安全协商失败',
  500: '运营商线路异常',
  501: '运营商不支持该能力',
  502: '运营商网关错误',
  503: '运营商线路繁忙',
  504: '运营商响应超时',
  505: '信令版本不受支持',
  513: '呼叫消息过大',
  580: '媒体预条件失败',
  600: '对方占线',
  603: '对方拒接',
  604: '该号码不存在',
  606: '对方无法接受此呼叫',
  607: '对方拒接',
  608: '对方拒接',
}

function sipFamilyHint(sip: number): string | null {
  if (sip >= 600 && sip < 700) return '对方无法接通'
  if (sip >= 500 && sip < 600) return '运营商线路异常'
  if (sip >= 400 && sip < 500) return '呼叫被拒绝'
  if (sip >= 300 && sip < 400) return '呼叫未能接通'
  return null
}

function sipHint(sip: number | null): string | null {
  if (sip == null) return null
  return SIP_STATUS_HINTS[sip] ?? sipFamilyHint(sip)
}

function coerceSipStatus(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) {
    return Number(value.trim())
  }
  return null
}

export function mapOutboundFailure(
  input: OutboundFailureInput,
): OutboundFailureMessage {
  const reason = (input.reason ?? '').trim()
  const sip = coerceSipStatus(input.sip_status)

  // ── Expected non-errors ──
  // agent_cancel: silent — the agent cancelled while ringing.
  // agent_hangup: silent — the agent hung up after the call was connected.
  // remote_bye: friendly notice — the callee hung up after talking; we
  // still want a brief toast so the agent isn't left wondering whether
  // the call actually ended or audio dropped.
  if (reason === 'agent_cancel' || reason === 'agent_hangup') {
    return { message: null, level: 'info', isFallback: false }
  }
  if (reason === 'remote_bye') {
    return { message: '对方已挂断', level: 'info', isFallback: false }
  }

  // Our 32s ring timeout cancels the INVITE; the leftover SIP is often
  // 180/183/487. Keep the timeout wording instead of "呼叫已取消".
  if (reason === 'local_cancel') {
    return { message: '振铃超时，对方未接听', level: 'error', isFallback: false }
  }

  // Final SIP responses are more specific than FlowKit's bucket reason
  // (rejected / originate_failed / busy). Prefer them whenever present.
  const sipMessage = sipHint(sip)
  if (sipMessage) {
    return { message: sipMessage, level: 'error', isFallback: false }
  }

  // ── Known failures without a SIP code ──
  if (reason === 'busy') {
    return { message: '对方占线，请稍后重试', level: 'error', isFallback: false }
  }
  if (reason === 'no_answer' || reason === 'timeout') {
    return { message: '对方未接听', level: 'error', isFallback: false }
  }
  if (reason === 'rejected' || reason === 'originate_rejected') {
    return { message: '通话被拒绝', level: 'error', isFallback: false }
  }
  if (reason === 'canceled') {
    return { message: '呼叫已取消', level: 'error', isFallback: false }
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
    reason === 'invite_failed' ||
    reason === 'ack_failed' ||
    reason === 'no_g711' ||
    reason === 'bad_answer_sdp' ||
    reason === 'mediaio_failed'
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
