'use client'
/**
 * Property panel — switches on selected node type and renders the matching
 * configuration form. All 6 panels live here to keep the surface compact.
 */
import { IconPlus, IconTrash } from '@tabler/icons-react'
import type { Node } from '@xyflow/react'

import { PromptInput } from './prompt-input'
import {
  COLLECT_OUTLET_COLOR,
  type AssignQueueData,
  type CollectData,
  type CollectMode,
  type ConditionData,
  type ConditionGroup,
  type ConditionItem,
  type ConditionOperator,
  type HangupData,
  type PlayData,
  defaultGroup,
} from '@/models/voice-flow-graph'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import { useServiceHours } from '@/service/use-service-hours'
import { useSystemVariables } from '@/service/use-system-variables'

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
  const { data: groups } = useEmployeeGroups({ page: 1, per_page: 100 })
  return (
    <>
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground/80">选择队列</label>
        <select
          value={data.employee_group_id ?? ''}
          onChange={(e) =>
            setData({
              employee_group_id: e.target.value ? Number(e.target.value) : null,
            })
          }
          className="h-9 w-full rounded-md border border-border bg-white px-2 text-sm"
        >
          <option value="">请选择员工组</option>
          {(groups?.items ?? []).map((g) => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
        <p className="mt-1 text-xs text-foreground/60">数据来源：员工组/技能组列表</p>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground/80">排队超时（秒）</label>
        <input
          type="number"
          value={data.timeout_seconds ?? ''}
          onChange={(e) =>
            setData({ timeout_seconds: e.target.value ? Number(e.target.value) : null })
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
