import type {
  CallEventDirection,
  CallEventSource,
  CallEventType,
} from '@/models/call-event-subscription'

type Text = { zh: string; en: string }

export type CallEventGroup = {
  title: Text
  events: Array<{ code: CallEventType; label: Text; hint: Text }>
}

export const CALL_EVENT_GROUPS: CallEventGroup[] = [
  {
    title: { zh: '通话生命周期', en: 'Call lifecycle' },
    events: [
      {
        code: 'call.created',
        label: { zh: '通话已创建', en: 'Call created' },
        hint: { zh: '已创建通话记录与初始轨迹', en: 'The call record and initial timeline were created' },
      },
      {
        code: 'call.customer.connected',
        label: { zh: '客户已接通', en: 'Customer connected' },
        hint: { zh: '呼入表示系统已接起，外呼表示客户已接听', en: 'Inbound: the system answered. Outbound: the customer answered' },
      },
      {
        code: 'call.ended',
        label: { zh: '通话已结束', en: 'Call ended' },
        hint: { zh: '结算完成，结果与时长已落库', en: 'Settlement finished with final result and durations' },
      },
    ],
  },
  {
    title: { zh: '排队与人工服务', en: 'Queue and agent service' },
    events: [
      {
        code: 'call.queue.entered',
        label: { zh: '已进入队列', en: 'Queue entered' },
        hint: { zh: '通话进入员工或员工组队列', en: 'The call entered an employee or group queue' },
      },
      {
        code: 'call.agent.connected',
        label: { zh: '坐席已接入', en: 'Agent connected' },
        hint: { zh: '坐席与客户建立人工服务段', en: 'An agent started serving the customer' },
      },
      {
        code: 'call.agent.disconnected',
        label: { zh: '坐席已离开', en: 'Agent disconnected' },
        hint: { zh: '一段人工服务结束', en: 'An agent service segment ended' },
      },
      {
        code: 'call.transfer.completed',
        label: { zh: '转接已完成', en: 'Transfer completed' },
        hint: { zh: '通话责任转移成功', en: 'Call ownership was transferred' },
      },
    ],
  },
  {
    title: { zh: '录音', en: 'Recording' },
    events: [
      {
        code: 'call.recording.completed',
        label: { zh: '录音已完成', en: 'Recording completed' },
        hint: { zh: '一个录音产物已完成或部分完成', en: 'A recording finished, fully or partially' },
      },
      {
        code: 'call.recording.failed',
        label: { zh: '录音失败', en: 'Recording failed' },
        hint: { zh: '一个录音产物失败', en: 'A recording failed' },
      },
    ],
  },
  {
    title: { zh: '满意度', en: 'Satisfaction' },
    events: [
      {
        code: 'call.satisfaction.completed',
        label: { zh: '满意度已完成', en: 'Satisfaction completed' },
        hint: { zh: '满意度调查已结束并完成投影', en: 'The satisfaction survey ended and was recorded' },
      },
    ],
  },
]

export const CALL_EVENT_LABELS = Object.fromEntries(
  CALL_EVENT_GROUPS.flatMap((group) => group.events.map((event) => [event.code, event.label])),
) as Record<CallEventType, Text>

export const CALL_DIRECTION_OPTIONS: Array<{ value: CallEventDirection; label: Text }> = [
  { value: 'inbound', label: { zh: '呼入', en: 'Inbound' } },
  { value: 'outbound', label: { zh: '外呼', en: 'Outbound' } },
]

export const CALL_SOURCE_OPTIONS: Array<{ value: CallEventSource; label: Text }> = [
  { value: 'inbound', label: { zh: '呼入', en: 'Inbound' } },
  { value: 'agent_dial', label: { zh: '坐席手动外呼', en: 'Agent manual dial' } },
  { value: 'embedded_call', label: { zh: '嵌入式通话', en: 'Embedded calling' } },
  { value: 'personal_auto_outbound', label: { zh: '客服个人自动外呼', en: 'Personal auto outbound' } },
  { value: 'manual_outbound_task', label: { zh: '人工外呼任务', en: 'Manual outbound task' } },
  { value: 'auto_outbound', label: { zh: '自动外呼', en: 'Auto outbound' } },
]

export const ALL_CALL_EVENT_TYPES = CALL_EVENT_GROUPS.flatMap((group) => group.events.map((event) => event.code))
export const ALL_CALL_DIRECTIONS = CALL_DIRECTION_OPTIONS.map((item) => item.value)
export const ALL_CALL_SOURCES = CALL_SOURCE_OPTIONS.map((item) => item.value)

export function pick(text: Text, isZh: boolean): string {
  return isZh ? text.zh : text.en
}

export function describeScope(
  directions: CallEventDirection[],
  sources: CallEventSource[],
  isZh: boolean,
): { summary: string; detail: string } {
  const allDirections = ALL_CALL_DIRECTIONS.every((value) => directions.includes(value))
  const allSources = ALL_CALL_SOURCES.every((value) => sources.includes(value))
  const directionLabels = CALL_DIRECTION_OPTIONS.filter((item) => directions.includes(item.value)).map((item) => pick(item.label, isZh))
  const sourceLabels = CALL_SOURCE_OPTIONS.filter((item) => sources.includes(item.value)).map((item) => pick(item.label, isZh))
  const directionText = allDirections ? (isZh ? '全部方向' : 'All directions') : directionLabels.join(isZh ? '、' : ', ')
  const sourceText = allSources
    ? (isZh ? '全部来源' : 'All sources')
    : isZh ? `${sources.length} 个来源` : `${sources.length} source${sources.length === 1 ? '' : 's'}`
  return {
    summary: `${directionText} · ${sourceText}`,
    detail: `${directionLabels.join(isZh ? '、' : ', ')}\n${sourceLabels.join(isZh ? '、' : ', ')}`,
  }
}
