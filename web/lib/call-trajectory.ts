import type { CallTrajectoryEvent } from '@/models/call-center'

const BUSINESS_EVENT_TYPES = new Set([
  'call_created', 'customer_connected', 'customer_ringing_started', 'ivr_entered',
  'ivr_exited', 'bot_started', 'bot_handoff_requested', 'bot_handoff_succeeded',
  'bot_ended', 'queue_entered', 'queue_exited', 'agent_offer_started',
  'reception_started', 'reception_ended', 'hold_started', 'hold_ended',
  'mute_started', 'mute_ended', 'dtmf_sent', 'transfer_started', 'consult_started',
  'conference_invite_started', 'supervisor_listen_started', 'supervisor_whisper_started',
  'supervisor_barge_started', 'supervisor_takeover_started',
  'supervisor_force_hangup_started', 'call_ending', 'call_ended',
  'human_service_ended', 'satisfaction_preparing', 'satisfaction_started',
  'satisfaction_question_answered', 'satisfaction_completed',
])

const LABELS: Record<string, [string, string]> = {
  call_created: ['收到客户呼叫', 'Call created'],
  customer_connected: ['客户线路已接通', 'Customer connected'],
  customer_ringing_started: ['客户振铃', 'Customer ringing'],
  ivr_entered: ['进入 IVR', 'Entered IVR'],
  ivr_exited: ['离开 IVR', 'Exited IVR'],
  bot_started: ['机器人开始接待', 'Bot service started'],
  bot_handoff_requested: ['机器人请求转人工', 'Bot requested handoff'],
  bot_handoff_succeeded: ['机器人转人工成功', 'Bot handoff succeeded'],
  bot_ended: ['机器人接待结束', 'Bot service ended'],
  queue_entered: ['进入等待队列', 'Entered queue'],
  queue_exited: ['离开等待队列', 'Left queue'],
  agent_offer_started: ['开始呼叫客服', 'Agent offer started'],
  agent_offer_accepted: ['客服已接听', 'Agent accepted'],
  agent_offer_rejected: ['客服已拒绝', 'Agent rejected'],
  agent_offer_timeout: ['客服未接听', 'Agent did not answer'],
  agent_offer_canceled: ['呼叫客服已取消', 'Agent call canceled'],
  reception_started: ['客服开始接待', 'Reception started'],
  reception_ended: ['客服接待结束', 'Reception ended'],
  hold_started: ['客户保持', 'Call placed on hold'],
  hold_ended: ['恢复通话', 'Call resumed'],
  mute_started: ['客服静音', 'Agent muted'],
  mute_ended: ['客服取消静音', 'Agent unmuted'],
  dtmf_sent: ['发送按键', 'DTMF sent'],
  transfer_started: ['发起转接', 'Transfer started'],
  transfer_target_ringing: ['目标客服振铃', 'Target agent ringing'],
  transfer_target_answered: ['目标客服已接听', 'Target agent answered'],
  transfer_completed: ['转接完成', 'Transfer completed'],
  transfer_failed: ['转接失败', 'Transfer failed'],
  consult_started: ['发起咨询', 'Consult started'],
  conference_invite_started: ['发起三方通话', 'Conference invitation started'],
  supervisor_listen_started: ['主管开始监听', 'Supervisor listening started'],
  supervisor_whisper_started: ['主管开始耳语', 'Supervisor whisper started'],
  supervisor_barge_started: ['主管开始强插', 'Supervisor barge started'],
  supervisor_takeover_started: ['主管发起接管', 'Supervisor takeover started'],
  supervisor_force_hangup_started: ['主管发起强制挂断', 'Supervisor force hangup started'],
  call_ending: ['通话进入结束流程', 'Call ending'],
  call_ended: ['通话结束', 'Call ended'],
  human_service_ended: ['人工服务结束', 'Human service ended'],
  satisfaction_preparing: ['发起满意度调查', 'Satisfaction survey requested'],
  satisfaction_started: ['客户进入满意度调查', 'Customer entered satisfaction survey'],
  satisfaction_question_answered: ['客户完成评价问题', 'Customer completed a survey question'],
  satisfaction_completed: ['满意度调查结束', 'Satisfaction survey ended'],
}

export function isBusinessTrajectoryEvent(event: CallTrajectoryEvent): boolean {
  return BUSINESS_EVENT_TYPES.has(event.event_type)
}

export function trajectoryEventLabel(eventType: string, isZh: boolean): string {
  const label = LABELS[eventType]
  if (label) return label[isZh ? 0 : 1]
  return eventType.replaceAll('_', ' ')
}

export function formatTrajectoryTime(value: string, technical = false): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const time = date.toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })
  return technical ? `${time}.${String(date.getMilliseconds()).padStart(3, '0')}` : time
}

export function formatTrajectoryDuration(durationMs: number | null | undefined, isZh = false): string {
  if (durationMs == null) return '-'
  if (durationMs < 1_000) return `${durationMs} ms`
  const seconds = Math.round(durationMs / 100) / 10
  if (seconds < 60) return `${seconds}${isZh ? ' 秒' : ' s'}`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

export function trajectoryEventDescription(
  event: CallTrajectoryEvent,
  isZh: boolean,
  technical: boolean,
  participantNames?: Map<string, string>,
): string {
  const actor = event.actor_name_snapshot
    || (!technical ? nameForId(participantNames, event.actor_id) : null)
    || event.actor_id
  const target = event.target_name_snapshot
    || event.queue_name_snapshot
    || (!technical ? nameForId(participantNames, event.target_id) : null)
    || event.target_id

  if (!technical) {
    if (event.event_type === 'satisfaction_preparing') {
      const source = event.details.trigger_source === 'agent_invite'
        ? (isZh ? '主动邀请' : 'Agent invite')
        : (isZh ? '自动转入' : 'Automatic')
      return `${actor || (isZh ? '客服' : 'Agent')} ${isZh ? '发起满意度调查' : 'started the survey'} (${source})`
    }
    if (event.event_type === 'satisfaction_started') {
      return target
        ? `${isZh ? '客户已进入满意度调查' : 'Customer entered survey'}: ${target}`
        : (isZh ? '客户已进入满意度调查' : 'Customer entered satisfaction survey')
    }
    if (event.event_type === 'satisfaction_question_answered') {
      const questionName = typeof event.details.question_name === 'string'
        ? event.details.question_name
        : target
      return questionName
        ? `${isZh ? '客户完成了' : 'Customer completed'} 《${questionName}》`
        : (isZh ? '客户完成了一道评价问题' : 'Customer completed a survey question')
    }
    if (event.event_type === 'satisfaction_completed') {
      const status = typeof event.details.status === 'string' ? event.details.status : event.result
      const labels: Record<string, [string, string]> = {
        completed: ['客户已完成满意度调查', 'Customer completed the satisfaction survey'],
        partial: ['满意度调查未完整完成', 'Satisfaction survey was partially completed'],
        unanswered: ['满意度调查未获得有效回答', 'Satisfaction survey received no valid answer'],
        failed: ['满意度调查启动失败', 'Satisfaction survey failed to start'],
      }
      const label = labels[status ?? '']?.[isZh ? 0 : 1]
      if (label) return event.reason_code ? `${label}: ${trajectoryReasonLabel(event.reason_code, isZh)}` : label
    }
    if (event.event_type === 'agent_offer_started' && target) {
      return `${isZh ? '客服' : 'Agent'} ${target}`
    }
    if (event.event_type === 'reception_started' && actor) {
      return `${isZh ? '客服' : 'Agent'} ${actor}`
    }
    if (event.event_type === 'reception_ended' && actor) {
      return `${isZh ? '原客服' : 'Previous agent'} ${actor}`
    }
    if (event.event_type === 'transfer_started' && actor && target) {
      return `${actor} → ${target}`
    }
  }

  const parts: string[] = []
  if (actor) parts.push(`${isZh ? '发起方' : 'Actor'} ${actor}`)
  if (target) parts.push(`${isZh ? '目标' : 'Target'} ${target}`)
  if (event.duration_ms != null) parts.push(`${isZh ? '耗时' : 'Duration'} ${formatTrajectoryDuration(event.duration_ms, isZh && !technical)}`)
  if (event.reason_code && (technical || event.reason_code !== 'normal')) {
    parts.push(`${isZh ? '原因' : 'Reason'} ${technical ? event.reason_code : trajectoryReasonLabel(event.reason_code, isZh)}`)
  }
  if (event.result && (technical || event.result !== 'succeeded')) {
    parts.push(`${isZh ? '结果' : 'Result'} ${technical ? event.result : trajectoryResultLabel(event.result, isZh)}`)
  }
  if (technical && event.source) parts.push(`${isZh ? '来源' : 'Source'} ${event.source}`)
  if (parts.length > 0) return parts.join(' · ')
  if (!technical && event.result) return trajectoryResultLabel(event.result, isZh)
  return isZh ? '暂无补充信息' : 'No additional details'
}

export function trajectoryParticipantNames(events: CallTrajectoryEvent[]): Map<string, string> {
  const names = new Map<string, string>()
  for (const event of events) {
    if (event.actor_id && event.actor_name_snapshot) names.set(event.actor_id, event.actor_name_snapshot)
    if (event.target_id && event.target_name_snapshot) names.set(event.target_id, event.target_name_snapshot)
  }
  return names
}

export function trajectoryResultLabel(result: string | null | undefined, isZh: boolean): string {
  if (!result) return isZh ? '进行中' : 'In progress'
  const labels: Record<string, [string, string]> = {
    succeeded: ['成功', 'Succeeded'],
    failed: ['失败', 'Failed'],
    rejected: ['已拒绝', 'Rejected'],
    timeout: ['超时', 'Timed out'],
    canceled: ['已取消', 'Canceled'],
    cancelled: ['已取消', 'Cancelled'],
    partial: ['部分完成', 'Partially completed'],
  }
  return labels[result]?.[isZh ? 0 : 1] ?? result.replaceAll('_', ' ')
}

export function trajectoryOperationTitle(
  events: CallTrajectoryEvent[],
  isZh: boolean,
  participantNames: Map<string, string>,
): string {
  const first = events[0]
  if (!first) return isZh ? '操作详情' : 'Operation details'
  if (first.event_type === 'agent_offer_started') {
    const agent = eventTarget(first, participantNames)
      || events.map((event) => eventActor(event, participantNames)).find(Boolean)
    return agent ? `${isZh ? '呼叫客服' : 'Call agent'} ${agent}` : trajectoryEventLabel(first.event_type, isZh)
  }
  if (first.event_type === 'transfer_started') {
    const actor = eventActor(first, participantNames)
    const target = eventTarget(first, participantNames)
    if (actor && target) return isZh ? `${actor} 转接给 ${target}` : `${actor} transferred to ${target}`
  }
  return trajectoryEventLabel(first.event_type, isZh)
}

export function trajectoryOperationStepLabel(eventType: string, isZh: boolean): string {
  if (eventType === 'reception_ended') return isZh ? '原客服结束接待' : 'Previous agent ended reception'
  if (eventType === 'reception_started') return isZh ? '新客服开始接待' : 'New agent started reception'
  return trajectoryEventLabel(eventType, isZh)
}

export function trajectoryOperationStepDescription(
  event: CallTrajectoryEvent,
  isZh: boolean,
  participantNames: Map<string, string>,
): string {
  const actor = eventActor(event, participantNames)
  const target = eventTarget(event, participantNames)
  if (event.event_type.startsWith('agent_offer_')) {
    const agent = target || actor
    return agent ? `${isZh ? '客服' : 'Agent'} ${agent}` : ''
  }
  if (event.event_type === 'reception_ended') {
    return actor ? `${isZh ? '原客服' : 'Previous agent'} ${actor}` : ''
  }
  if (event.event_type === 'reception_started') {
    return actor ? `${isZh ? '新客服' : 'New agent'} ${actor}` : ''
  }
  if (event.event_type.startsWith('transfer_')) {
    if (actor && target) return `${actor} → ${target}`
    if (target) return `${isZh ? '目标客服' : 'Target agent'} ${target}`
    return actor || ''
  }
  if (actor && target) return `${actor} → ${target}`
  return actor || target || ''
}

function trajectoryReasonLabel(reason: string, isZh: boolean): string {
  const labels: Record<string, [string, string]> = {
    agent_no_answer: ['客服未接听', 'Agent did not answer'],
    agent_rejected: ['客服已拒绝', 'Agent rejected'],
    bridge_failed: ['通话桥接失败', 'Call bridge failed'],
    target_unavailable: ['目标客服不可用', 'Target agent unavailable'],
    transfer_completed: ['转接完成', 'Transfer completed'],
    call_ended: ['通话结束', 'Call ended'],
    recording_failed: ['录音失败', 'Recording failed'],
  }
  return labels[reason]?.[isZh ? 0 : 1] ?? reason.replaceAll('_', ' ')
}

function eventActor(event: CallTrajectoryEvent, participantNames: Map<string, string>): string | null {
  return event.actor_name_snapshot || nameForId(participantNames, event.actor_id) || event.actor_id
}

function eventTarget(event: CallTrajectoryEvent, participantNames: Map<string, string>): string | null {
  return event.target_name_snapshot
    || event.queue_name_snapshot
    || nameForId(participantNames, event.target_id)
    || event.target_id
}

function nameForId(participantNames: Map<string, string> | undefined, id: string | null): string | null {
  return id ? participantNames?.get(id) ?? null : null
}
