/**
 * Voice flow validation error parser.
 *
 * Two backend error shapes need to be unified into a single UI-friendly
 * `ValidationIssue[]`:
 *
 * 1. **Pydantic 422** — request schema validation. Body shape:
 *    `{ detail: [{ type, loc: [...path...], msg, input, ctx }] }`
 *    `loc` is like:
 *    `["body","graph_json","nodes", 1, "play", "data","prompt","tts","text"]`
 *    The integer right after `"nodes"` is the node array index; the
 *    string after it (`"play"`) is the discriminator tag.
 *
 * 2. **Custom `_validate_graph` 400** — business rules. Body shape:
 *    `{ code: "VALIDATION_ERROR", details: { errors: [{node_id?, field?, code, message}, ...] } }`
 */
import type { Node } from '@xyflow/react'

export type ValidationIssue = {
  /** Node id if we could resolve it from the path. */
  nodeId?: string
  /** Index into the nodes array (Pydantic only). */
  nodeIndex?: number
  /** Node type / discriminator (`play`, `collect`, ...). */
  nodeType?: string
  /** Human-readable field path inside the node, e.g. "提示音 · TTS 文案". */
  fieldLabel?: string
  /** Final, localized message shown to the user. */
  message: string
}

const NODE_TYPE_LABEL: Record<string, string> = {
  start: '开始',
  play: '纯语音',
  collect: '收集输入',
  condition: '信息判定',
  assign_queue: '分配队列',
  hangup: '挂断',
}

// Common backend field paths → friendly label.
const FIELD_LABELS: Array<{ test: RegExp; label: string }> = [
  { test: /^prompt\.tts\.text$/,             label: '提示音 · TTS 文案' },
  { test: /^prompt\.audio\.asset_id$/,       label: '提示音 · 音频资源' },
  { test: /^prompt$/,                        label: '提示音' },
  { test: /^pre_play\.tts\.text$/,           label: '挂断前播放 · TTS 文案' },
  { test: /^pre_play\.audio\.asset_id$/,     label: '挂断前播放 · 音频资源' },
  { test: /^input\.min_digits$/,             label: 'DTMF · 最短位数' },
  { test: /^input\.max_digits$/,             label: 'DTMF · 最长位数' },
  { test: /^input\.terminator$/,             label: 'DTMF · 结束键' },
  { test: /^input$/,                         label: 'DTMF 输入配置' },
  { test: /^timeout\.first_input_ms$/,       label: '超时 · 首次等待' },
  { test: /^timeout\.inter_digit_ms$/,       label: '超时 · 按键间隔' },
  { test: /^retry\.no_input$/,               label: '重试 · 无输入次数' },
  { test: /^retry\.no_match$/,               label: '重试 · 无匹配次数' },
  { test: /^output_variable$/,               label: '输出变量名' },
  { test: /^employee_group_id$/,             label: '员工组' },
  { test: /^timeout_seconds$/,               label: '排队超时' },
  { test: /^groups\.(\d+)\.name$/,           label: '条件组名称' },
  { test: /^groups\.(\d+)\.conditions\.(\d+)\.variable$/, label: '条件 · 变量' },
  { test: /^groups\.(\d+)\.conditions\.(\d+)\.operator$/, label: '条件 · 操作符' },
  { test: /^groups\.(\d+)\.conditions\.(\d+)\.value$/,    label: '条件 · 值' },
]

function humanizeField(fieldPath: string): string {
  for (const { test, label } of FIELD_LABELS) {
    if (test.test(fieldPath)) return label
  }
  return fieldPath || '该节点'
}

function humanizePydanticMsg(item: PydanticErrorItem): string {
  const t = item.type
  const ctx = item.ctx ?? {}
  switch (t) {
    case 'string_too_short':
      return `不能为空（最少 ${ctx.min_length ?? 1} 个字符）`
    case 'string_too_long':
      return `字符过长（最多 ${ctx.max_length ?? '?'} 字符）`
    case 'missing':
      return '缺少必填字段'
    case 'value_error':
      return item.msg.replace(/^Value error,\s*/, '')
    case 'int_parsing':
    case 'int_type':
      return '需要整数'
    case 'greater_than_equal':
      return `值需 ≥ ${ctx.ge ?? '?'}`
    case 'less_than_equal':
      return `值需 ≤ ${ctx.le ?? '?'}`
    case 'enum':
      return `非法的选项${ctx.expected ? `（应为 ${ctx.expected}）` : ''}`
    case 'literal_error':
      return `非法的选项${ctx.expected ? `（应为 ${ctx.expected}）` : ''}`
    case 'union_tag_invalid':
      return '类型选择无效'
    case 'extra_forbidden':
      return '存在未识别的字段'
    case 'string_pattern_mismatch':
      return '格式不正确'
    default:
      return item.msg
  }
}

const CUSTOM_CODE_MSG: Record<string, string> = {
  start_node_missing: '缺少开始节点',
  edge_source_missing: '连线起点节点不存在',
  edge_target_missing: '连线终点节点不存在',
  invalid_source_handle: '连线出口与节点不匹配',
  missing_next_edge: '该节点没有连接到下一节点',
  missing_success_edge: '「成功」出口未连线',
  missing_default_edge: '「默认」出口未连线',
  missing_group_edge: '某个条件组的出口未连线',
  audio_asset_not_found: '引用的音频资源不存在或已删除',
  queue_not_found: '引用的员工组不存在',
  service_hours_not_found: '引用的服务时间不存在',
  variable_not_produced: '变量未在任何收集节点中定义',
  variable_not_reachable: '变量来源节点不在当前节点的上游路径上',
}

type PydanticErrorItem = {
  type: string
  loc: Array<string | number>
  msg: string
  input?: unknown
  ctx?: Record<string, unknown> & { min_length?: number; max_length?: number; ge?: number; le?: number; expected?: string }
}

type CustomError = {
  node_id?: string | null
  field?: string | null
  code: string
  message: string
}

type ErrorBody = {
  detail?: PydanticErrorItem[]
  details?: { errors?: CustomError[] }
}

export function parseValidationErrors(
  body: unknown,
  nodes: Node[],
): ValidationIssue[] {
  if (!body || typeof body !== 'object') return []
  const b = body as ErrorBody

  // Custom format from VoiceFlowService._validate_graph
  if (Array.isArray(b.details?.errors)) {
    return b.details.errors.map((e) => ({
      nodeId: e.node_id ?? undefined,
      nodeType: e.node_id ? nodes.find((n) => n.id === e.node_id)?.type ?? undefined : undefined,
      fieldLabel: e.field ? humanizeField(stripNodeTypeFromField(e.field)) : undefined,
      message: CUSTOM_CODE_MSG[e.code] ?? e.message,
    }))
  }

  // Pydantic 422 format
  if (Array.isArray(b.detail)) {
    return b.detail.map((d) => fromPydanticItem(d, nodes))
  }

  return []
}

function stripNodeTypeFromField(field: string): string {
  // `field` from custom errors is sometimes like "outlet:next" or "groups[g1].conditions.variable".
  // Normalize the common cases for humanizeField().
  if (field.startsWith('outlet:')) return field
  return field.replace(/\[(\w+)\]/g, '.$1').replace(/^edges\.[^.]+\./, '')
}

function fromPydanticItem(d: PydanticErrorItem, nodes: Node[]): ValidationIssue {
  const loc = d.loc || []
  const nodesIdx = loc.indexOf('nodes')

  let nodeIndex: number | undefined
  let nodeId: string | undefined
  let nodeType: string | undefined
  let fieldPath = ''

  if (nodesIdx >= 0 && typeof loc[nodesIdx + 1] === 'number') {
    nodeIndex = loc[nodesIdx + 1] as number
    const node = nodes[nodeIndex]
    if (node) {
      nodeId = node.id
      nodeType = node.type
    }
    // After the index there's typically a type-tag (e.g. "play") used by the
    // discriminator — skip it. Then "data" — also skip and start the
    // user-visible path from there.
    let rest = loc.slice(nodesIdx + 2)
    if (rest.length > 0 && typeof rest[0] === 'string' && rest[0] in NODE_TYPE_LABEL) {
      rest = rest.slice(1)
    }
    if (rest[0] === 'data') rest = rest.slice(1)
    fieldPath = rest.map(String).join('.')
  } else {
    fieldPath = loc.map(String).join('.')
  }

  return {
    nodeId,
    nodeIndex,
    nodeType,
    fieldLabel: fieldPath ? humanizeField(fieldPath) : undefined,
    message: humanizePydanticMsg(d),
  }
}

export function formatIssueHeadline(issue: ValidationIssue, nodes: Node[]): string {
  const node = issue.nodeId ? nodes.find((n) => n.id === issue.nodeId) : null
  const nodeTypeLabel = node?.type ? NODE_TYPE_LABEL[node.type as string] : (issue.nodeType ? NODE_TYPE_LABEL[issue.nodeType] : '')
  const idPart = node ? ` #${node.id}` : ''
  const nodePart = nodeTypeLabel ? `${nodeTypeLabel}${idPart}` : '画布'
  const field = issue.fieldLabel ? ` · ${issue.fieldLabel}` : ''
  return `${nodePart}${field}：${issue.message}`
}
