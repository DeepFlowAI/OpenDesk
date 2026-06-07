'use client'
/**
 * Property panel — switches on selected node type and renders the matching
 * configuration form. All 6 panels live here to keep the surface compact.
 */
import {
  IconArrowDown,
  IconArrowUp,
  IconChevronDown,
  IconGripVertical,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import type { Node } from '@xyflow/react'

import { PromptInput } from './prompt-input'
import {
  COLLECT_OUTLET_COLOR,
  type AssignQueueData,
  type AssignQueueTarget,
  type AssignQueueTargetStrategy,
  type AssignQueueTargetType,
  type CollectData,
  type CollectMode,
  type ConditionData,
  type ConditionGroup,
  type ConditionItem,
  type ConditionOperator,
  type HangupData,
  type PlayData,
  defaultAssignQueueData,
  defaultGroup,
} from '@/models/voice-flow-graph'
import { useEmployeeGroups, useEmployeeSelect } from '@/service/use-employee-groups'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useServiceHours } from '@/service/use-service-hours'
import { useSystemVariables } from '@/service/use-system-variables'
import { FieldDomain, FieldType } from '@/types/field-enums'

type SelectableNode = { id: string; type: string; label: string }

export function PropertyPanel({
  selected,
  updateNode,
  allNodes,
  graphVariables,
}: {
  selected: Node | null
  updateNode: (id: string, patch: { data?: Record<string, unknown> }) => void
  allNodes: SelectableNode[]
  graphVariables: string[]
}) {
  if (!selected) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
        点击画布上的节点以编辑其配置
      </div>
    )
  }
  const id = selected.id
  const type = selected.type as string

  const setData = <T,>(patch: Partial<T>) =>
    updateNode(id, { data: { ...(selected.data as object), ...patch } })

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h3 className="text-base font-semibold text-foreground">{typeLabel(type)}</h3>
        <span className="rounded bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">{type}</span>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
        {type === 'start' && <StartPanel />}
        {type === 'play' && (
          <PlayPanel
            data={selected.data as PlayData}
            setData={setData<PlayData>}
            allNodes={allNodes}
          />
        )}
        {type === 'collect' && (
          <CollectPanel
            data={selected.data as CollectData}
            setData={setData<CollectData>}
          />
        )}
        {type === 'condition' && (
          <ConditionPanel
            data={selected.data as ConditionData}
            setData={setData<ConditionData>}
            graphVariables={graphVariables}
          />
        )}
        {type === 'assign_queue' && (
          <AssignQueuePanel
            data={selected.data as AssignQueueData}
            setData={setData<AssignQueueData>}
          />
        )}
        {type === 'hangup' && (
          <HangupPanel data={selected.data as HangupData} setData={setData<HangupData>} />
        )}
      </div>
    </div>
  )
}

function typeLabel(t: string): string {
  switch (t) {
    case 'start': return '开始'
    case 'play': return '纯语音'
    case 'collect': return '收集输入'
    case 'condition': return '信息判定'
    case 'assign_queue': return '分配队列'
    case 'hangup': return '挂断'
    default: return t
  }
}

// ─────────────── start ───────────────

function StartPanel() {
  return (
    <div className="rounded-lg bg-muted/50 p-3 text-sm text-foreground/80">
      流程入口节点，每个语音流程有且仅有一个开始节点。无需配置。
      <p className="mt-2 text-xs text-foreground/60">从开始节点拖拽连线到下一个节点。</p>
    </div>
  )
}

// ─────────────── play ───────────────

function PlayPanel({
  data,
  setData,
}: {
  data: PlayData
  setData: (p: Partial<PlayData>) => void
  allNodes: SelectableNode[]
}) {
  return (
    <>
      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">播报内容设置</h4>
        <PromptInput value={data.prompt} onChange={(v) => setData({ prompt: v })} />
      </section>
      <p className="text-xs text-foreground/60">出口在画布上拖拽至下一节点；与属性面板下拉互通（暂未实现下拉）。</p>
    </>
  )
}

// ─────────────── collect ───────────────

function CollectPanel({
  data,
  setData,
}: {
  data: CollectData
  setData: (p: Partial<CollectData>) => void
}) {
  return (
    <>
      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">A. 提示音设置</h4>
        <PromptInput value={data.prompt} onChange={(v) => setData({ prompt: v })} label="提示音" />
        <label className="mt-2 flex items-center gap-2 text-xs text-foreground/80">
          <input
            type="checkbox"
            checked={data.barge_in_disabled}
            onChange={(e) => setData({ barge_in_disabled: e.target.checked })}
          />
          禁止提示音期间输入
        </label>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">B. DTMF 输入</h4>
        <div className="space-y-2">
          <select
            value={data.input.mode}
            onChange={(e) =>
              setData({
                input: { ...data.input, mode: e.target.value as CollectMode },
              })
            }
            className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
          >
            <option value="single">单位数字</option>
            <option value="multi">多位数字</option>
            <option value="any">任意按键</option>
          </select>
          {data.input.mode === 'multi' && (
            <div className="grid grid-cols-2 gap-2">
              <NumberField
                label="最短"
                value={data.input.min_digits}
                onChange={(v) => setData({ input: { ...data.input, min_digits: v } })}
              />
              <NumberField
                label="最长"
                value={data.input.max_digits}
                onChange={(v) => setData({ input: { ...data.input, max_digits: v } })}
              />
            </div>
          )}
          {(data.input.mode === 'multi' || data.input.mode === 'any') && (
            <select
              value={data.input.terminator ?? '#'}
              onChange={(e) =>
                setData({
                  input: { ...data.input, terminator: e.target.value as '#' | '*' },
                })
              }
              className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
            >
              <option value="#">结束键 #</option>
              <option value="*">结束键 *</option>
            </select>
          )}
        </div>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">C. 超时设置</h4>
        <div className="grid grid-cols-2 gap-2">
          <NumberField
            label="首次输入 (ms)"
            value={data.timeout.first_input_ms}
            onChange={(v) => setData({ timeout: { ...data.timeout, first_input_ms: v } })}
          />
          <NumberField
            label="按键间隔 (ms)"
            value={data.timeout.inter_digit_ms}
            onChange={(v) => setData({ timeout: { ...data.timeout, inter_digit_ms: v } })}
          />
        </div>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">D. 重试设置</h4>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={data.retry.enabled}
            onChange={(e) => setData({ retry: { ...data.retry, enabled: e.target.checked } })}
          />
          启用重试
        </label>
        {data.retry.enabled && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <NumberField
              label="无输入次数"
              value={data.retry.no_input}
              onChange={(v) => setData({ retry: { ...data.retry, no_input: v } })}
            />
            <NumberField
              label="无匹配次数"
              value={data.retry.no_match}
              onChange={(v) => setData({ retry: { ...data.retry, no_match: v } })}
            />
          </div>
        )}
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">E. 变量输出</h4>
        <input
          type="text"
          value={data.output_variable}
          onChange={(e) => setData({ output_variable: e.target.value })}
          className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm font-mono"
          placeholder="user_input"
        />
        <p className="mt-1 text-xs text-foreground/60">字母/下划线开头，仅字母、数字、下划线</p>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-foreground">F. 出口</h4>
        <ul className="space-y-2 text-xs">
          {[
            { k: 'success', l: '成功', desc: '必须连线' },
            { k: 'no_input', l: '无输入', desc: '可选' },
            { k: 'no_match', l: '无匹配', desc: '可选' },
            { k: 'error', l: '错误', desc: '可选' },
          ].map((o) => (
            <li
              key={o.k}
              className="flex items-center gap-2 rounded-md border border-border px-2 py-1.5"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: COLLECT_OUTLET_COLOR[o.k] }}
              />
              <span className="font-medium">{o.l}</span>
              <span className="ml-auto text-foreground/60">{o.desc}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

function NumberField({
  label, value, onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div>
      <label className="mb-1 block text-[11px] text-foreground/70">{label}</label>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
      />
    </div>
  )
}

// ─────────────── condition ───────────────

function ConditionPanel({
  data, setData, graphVariables,
}: {
  data: ConditionData
  setData: (p: Partial<ConditionData>) => void
  graphVariables: string[]
}) {
  const { data: sysVars } = useSystemVariables()
  const { data: srvHours } = useServiceHours()
  const variables = [
    ...(sysVars?.items.map((v) => v.name) ?? []),
    ...graphVariables,
  ]

  const updateGroup = (gi: number, patch: Partial<ConditionGroup>) => {
    const groups = [...data.groups]
    groups[gi] = { ...groups[gi], ...patch }
    setData({ groups })
  }
  const updateCond = (gi: number, ci: number, patch: Partial<ConditionItem>) => {
    const groups = [...data.groups]
    const conds = [...groups[gi].conditions]
    conds[ci] = { ...conds[ci], ...patch }
    groups[gi] = { ...groups[gi], conditions: conds }
    setData({ groups })
  }

  return (
    <>
      {data.groups.map((g, gi) => (
        <section key={g.id} className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between">
            <input
              type="text"
              value={g.name}
              onChange={(e) => updateGroup(gi, { name: e.target.value })}
              className="h-8 w-32 rounded-md border border-border px-2 text-sm font-medium"
            />
            <select
              value={g.logic}
              onChange={(e) => updateGroup(gi, { logic: e.target.value as 'AND' | 'OR' })}
              className="h-8 rounded-md border border-border px-2 text-sm"
            >
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
            {data.groups.length > 1 && (
              <button
                type="button"
                onClick={() => setData({ groups: data.groups.filter((_, i) => i !== gi) })}
                className="text-red-600"
                aria-label="删除组"
              >
                <IconTrash size={14} />
              </button>
            )}
          </div>

          <div className="mt-2 space-y-1.5">
            {g.conditions.map((c, ci) => (
              <div key={ci} className="flex items-center gap-1">
                <select
                  value={c.variable}
                  onChange={(e) => updateCond(gi, ci, { variable: e.target.value })}
                  className="h-8 flex-1 min-w-0 rounded-md border border-border px-1 text-xs"
                >
                  {variables.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                <select
                  value={c.operator}
                  onChange={(e) =>
                    updateCond(gi, ci, { operator: e.target.value as ConditionOperator })
                  }
                  className="h-8 w-24 shrink-0 rounded-md border border-border px-1 text-xs"
                >
                  <option value="eq">等于</option>
                  <option value="neq">不等于</option>
                  <option value="any_eq">任意等于</option>
                  <option value="any_neq">任意不等于</option>
                  <option value="is_empty">为空</option>
                  <option value="is_not_empty">不为空</option>
                  <option value="time_in">属于(时段)</option>
                  <option value="time_not_in">不属于(时段)</option>
                </select>
                {c.operator === 'time_in' || c.operator === 'time_not_in' ? (
                  <select
                    value={typeof c.value === 'number' ? c.value : ''}
                    onChange={(e) => updateCond(gi, ci, { value: Number(e.target.value) })}
                    className="h-8 w-24 shrink-0 rounded-md border border-border px-1 text-xs"
                  >
                    <option value="">选择...</option>
                    {(srvHours ?? []).map((sh) => (
                      <option key={sh.id} value={sh.id}>{sh.name}</option>
                    ))}
                  </select>
                ) : c.operator === 'is_empty' || c.operator === 'is_not_empty' ? (
                  <span className="w-24 shrink-0 text-center text-xs text-foreground/50">—</span>
                ) : (
                  <input
                    type="text"
                    value={typeof c.value === 'string' ? c.value : ''}
                    onChange={(e) => updateCond(gi, ci, { value: e.target.value })}
                    className="h-8 w-24 shrink-0 rounded-md border border-border px-1 text-xs"
                  />
                )}
                <button
                  type="button"
                  className="shrink-0 text-foreground/60 hover:text-red-600"
                  onClick={() =>
                    updateGroup(gi, { conditions: g.conditions.filter((_, i) => i !== ci) })
                  }
                  disabled={g.conditions.length === 1}
                  aria-label="删除条件"
                >
                  <IconTrash size={12} />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() =>
                updateGroup(gi, {
                  conditions: [
                    ...g.conditions,
                    { variable: 'sys.caller_number', operator: 'eq', value: '' },
                  ],
                })
              }
              className="flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <IconPlus size={12} /> 添加条件
            </button>
          </div>
        </section>
      ))}

      <button
        type="button"
        onClick={() => setData({ groups: [...data.groups, defaultGroup()] })}
        className="flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border py-2 text-xs text-primary"
      >
        <IconPlus size={14} /> 添加条件组
      </button>

      <p className="text-xs text-foreground/60">默认出口：当所有条件组都未命中时走默认出口（必须连线）。</p>
    </>
  )
}

// ─────────────── assign_queue ───────────────

function AssignQueuePanel({
  data, setData,
}: {
  data: AssignQueueData
  setData: (p: Partial<AssignQueueData>) => void
}) {
  const { data: groups } = useEmployeeGroups({ page: 1, per_page: 200 })
  const { data: employees } = useEmployeeSelect({ page: 1, per_page: 200 })
  const { data: userFields } = useUnifiedFields({
    domain: FieldDomain.USER,
    include_metadata: false,
  })
  const normalized = normalizeAssignQueueData(data)
  const queueTargets = normalized.queue_targets
  const queueFields =
    userFields?.items.filter(
      (field) =>
        field.id != null &&
        field.status === 'active' &&
        (field.field_type === FieldType.EMPLOYEE_SELECT || field.field_type === FieldType.GROUP_SELECT),
    ) ?? []

  const patch = (p: Partial<AssignQueueData>) =>
    setData({ ...normalized, employee_group_id: null, ...p })
  const updateTarget = (index: number, next: Partial<AssignQueueTarget>) => {
    const queue_targets = queueTargets.map((target, i) => {
      if (i !== index) return target
      const merged = { ...target, ...next }
      if (next.queue_type && next.queue_type !== target.queue_type) {
        merged.queue_id = null
      }
      return merged
    })
    patch({ queue_targets })
  }
  const removeTarget = (index: number) => {
    const next = queueTargets.filter((_, i) => i !== index)
    patch({
      queue_targets: next.length
        ? next
        : [{ queue_type: 'employee_group', queue_id: null }],
    })
  }
  const moveTarget = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= queueTargets.length) return
    const next = [...queueTargets]
    const [item] = next.splice(index, 1)
    next.splice(nextIndex, 0, item)
    patch({ queue_targets: next })
  }

  return (
    <>
      <section className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-foreground/80">多队列选择方式</label>
          <div className="relative">
            <select
              value={normalized.target_strategy}
              onChange={(e) =>
                patch({ target_strategy: e.target.value as AssignQueueTargetStrategy })
              }
              className="h-9 w-full appearance-none rounded-md border border-border bg-white px-2 pr-8 text-sm"
            >
              <option value="sequential_overflow">顺序溢出</option>
              <option value="least_waiting_count">最少排队队列</option>
              <option value="shortest_tail_wait">最短排队时间队列</option>
            </select>
            <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
          </div>
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-xs font-medium text-foreground/80">候选队列</label>
            <span className="text-[11px] text-foreground/50">{queueTargets.length}/20</span>
          </div>
          <div className="overflow-hidden rounded-md border border-border">
            {queueTargets.map((target, index) => (
              <div
                key={`${index}-${target.queue_type}-${target.queue_id ?? 'empty'}`}
                className="grid grid-cols-[24px_86px_minmax(0,1fr)_28px] items-center gap-2 border-b border-border px-2 py-2 last:border-b-0"
              >
                <div className="flex flex-col items-center justify-center gap-0.5 text-muted-foreground">
                  <IconGripVertical size={14} />
                  <div className="flex gap-0.5 text-[10px] leading-none">
                    <button
                      type="button"
                      onClick={() => moveTarget(index, -1)}
                      disabled={index === 0}
                      className="disabled:opacity-30"
                      aria-label="上移队列目标"
                    >
                      <IconArrowUp size={10} />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveTarget(index, 1)}
                      disabled={index === queueTargets.length - 1}
                      className="disabled:opacity-30"
                      aria-label="下移队列目标"
                    >
                      <IconArrowDown size={10} />
                    </button>
                  </div>
                </div>

                <select
                  value={target.queue_type}
                  onChange={(e) =>
                    updateTarget(index, { queue_type: e.target.value as AssignQueueTargetType })
                  }
                  className="h-8 rounded-md border border-border bg-white px-2 text-xs"
                >
                  <option value="user_field">用户字段</option>
                  <option value="employee">员工</option>
                  <option value="employee_group">员工组</option>
                </select>

                {target.queue_type === 'user_field' ? (
                  <select
                    value={target.queue_id ?? ''}
                    onChange={(e) =>
                      updateTarget(index, { queue_id: e.target.value ? Number(e.target.value) : null })
                    }
                    className="h-8 min-w-0 rounded-md border border-border bg-white px-2 text-xs"
                  >
                    <option value="">请选择用户字段</option>
                    {queueFields.map((field) => (
                      <option key={field.id} value={field.id ?? ''}>
                        {field.name}
                      </option>
                    ))}
                  </select>
                ) : target.queue_type === 'employee' ? (
                  <select
                    value={target.queue_id ?? ''}
                    onChange={(e) =>
                      updateTarget(index, { queue_id: e.target.value ? Number(e.target.value) : null })
                    }
                    className="h-8 min-w-0 rounded-md border border-border bg-white px-2 text-xs"
                  >
                    <option value="">请选择员工</option>
                    {(employees?.items ?? []).map((employee) => (
                      <option key={employee.id} value={employee.id}>
                        {employee.display_name || employee.username}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select
                    value={target.queue_id ?? ''}
                    onChange={(e) =>
                      updateTarget(index, { queue_id: e.target.value ? Number(e.target.value) : null })
                    }
                    className="h-8 min-w-0 rounded-md border border-border bg-white px-2 text-xs"
                  >
                    <option value="">请选择员工组</option>
                    {(groups?.items ?? []).map((g) => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                )}

                <button
                  type="button"
                  onClick={() => removeTarget(index)}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-red-600"
                  aria-label="删除队列目标"
                >
                  <IconTrash size={14} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() =>
              queueTargets.length < 20 &&
              patch({
                queue_targets: [
                  ...queueTargets,
                  { queue_type: 'employee_group', queue_id: null },
                ],
              })
            }
            disabled={queueTargets.length >= 20}
            className="mt-2 flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border py-2 text-xs text-primary disabled:opacity-40"
          >
            <IconPlus size={14} /> 添加队列目标
          </button>
          <p className="mt-1 text-xs text-foreground/60">
            顺序溢出时列表顺序表示尝试顺序；其它策略中用于并列兜底。
          </p>
        </div>
      </section>

      <section className="space-y-3">
        <h4 className="text-sm font-semibold text-foreground">排队提示设置</h4>
        <TextAreaField
          label="排队提示话术"
          value={normalized.queue_prompt_text}
          onChange={(value) => patch({ queue_prompt_text: value })}
          placeholder="正在为您转接，请稍候。"
        />
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground/80">播放方式</label>
            <select
              value={normalized.prompt_play_mode}
              onChange={(e) => patch({ prompt_play_mode: e.target.value as 'once' | 'loop' })}
              className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
            >
              <option value="once">仅播放一次</option>
              <option value="loop">循环播放</option>
            </select>
          </div>
          {normalized.prompt_play_mode === 'loop' && (
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground/80">循环间隔（秒）</label>
              <input
                type="number"
                value={normalized.prompt_loop_interval_seconds ?? ''}
                onChange={(e) =>
                  patch({
                    prompt_loop_interval_seconds: e.target.value ? Number(e.target.value) : null,
                  })
                }
                className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
                placeholder="例如 15"
              />
            </div>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h4 className="text-sm font-semibold text-foreground">失败状态提示</h4>
        <TextAreaField
          label="达到排队上限"
          value={normalized.queue_limit_prompt_text}
          onChange={(value) => patch({ queue_limit_prompt_text: value })}
        />
        <TextAreaField
          label="无可用队列"
          value={normalized.no_available_queue_prompt_text}
          onChange={(value) => patch({ no_available_queue_prompt_text: value })}
        />
        <TextAreaField
          label="排队超时"
          value={normalized.queue_timeout_prompt_text}
          onChange={(value) => patch({ queue_timeout_prompt_text: value })}
        />
        <TextAreaField
          label="坐席未接听"
          value={normalized.agent_no_answer_prompt_text}
          onChange={(value) => patch({ agent_no_answer_prompt_text: value })}
        />
      </section>

      <div>
        <label className="mb-1 block text-xs font-medium text-foreground/80">排队超时（秒）</label>
        <input
          type="number"
          value={normalized.timeout_seconds ?? ''}
          onChange={(e) =>
            patch({ timeout_seconds: e.target.value ? Number(e.target.value) : null })
          }
          className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
          placeholder="例如 60"
        />
      </div>
      <p className="text-xs text-foreground/60">
        接通后通话由 FlowKit 直接桥接给坐席浏览器，本节点之后流程自动结束；
        无需再接下一节点。
        <br />
        如需在「排队超时未分到坐席」时走自定义路径，把 <code>timeout</code> 出口连到下一节点（通常是挂断或挂断前播报）。
      </p>
    </>
  )
}

function normalizeAssignQueueData(data: AssignQueueData): AssignQueueData {
  const defaults = defaultAssignQueueData()
  const queueTargets =
    data.queue_targets?.length
      ? data.queue_targets
      : data.employee_group_id
        ? [{ queue_type: 'employee_group' as const, queue_id: data.employee_group_id }]
        : defaults.queue_targets
  return {
    ...defaults,
    ...data,
    queue_targets: queueTargets,
  }
}

function TextAreaField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-foreground/80">{label}</label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-h-16 w-full resize-y rounded-md border border-border bg-white px-2 py-2 text-sm"
        maxLength={300}
        placeholder={placeholder}
      />
      <div className="mt-0.5 text-right text-[11px] text-foreground/50">{value.length}/300</div>
    </div>
  )
}

// ─────────────── hangup ───────────────

function HangupPanel({
  data, setData,
}: {
  data: HangupData
  setData: (p: Partial<HangupData>) => void
}) {
  return (
    <>
      <label className="flex items-center justify-between gap-2 text-sm">
        挂断前播放
        <input
          type="checkbox"
          checked={data.pre_play != null}
          onChange={(e) =>
            setData({ pre_play: e.target.checked ? { kind: 'tts', text: '' } : null })
          }
        />
      </label>
      {data.pre_play && (
        <div className="rounded-md bg-muted/40 p-3">
          <PromptInput
            value={data.pre_play}
            onChange={(v) => setData({ pre_play: v })}
            label="挂断前播放"
          />
        </div>
      )}
      <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
        挂断节点为终端节点，通话将在此结束。
      </div>
    </>
  )
}
