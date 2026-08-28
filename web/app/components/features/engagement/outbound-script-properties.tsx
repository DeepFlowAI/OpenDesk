'use client'

import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from '@tabler/icons-react'

import type { OutboundScriptNode, OutboundScriptNodeType } from '@/models/outbound-task'
import { outboundScriptNodeLabel } from './outbound-script-utils'
import { OutboundScriptRichText } from './outbound-script-rich-text'

export function OutboundScriptProperties({ node, onChange, onAddChild, onDelete, onRemoveBranch }: {
  node: OutboundScriptNode
  onChange: (node: OutboundScriptNode) => void
  onAddChild: (type: Exclude<OutboundScriptNodeType, 'start'>, branchId?: string) => void
  onDelete: (nodeId: string) => void
  onRemoveBranch: (branchId: string) => void
}) {
  const update = <K extends keyof OutboundScriptNode>(key: K, value: OutboundScriptNode[K]) => onChange({ ...node, [key]: value })
  const addBranch = () => {
    if (node.branches.length >= 8) return
    update('branches', [...node.branches, { id: `option-${crypto.randomUUID()}`, label: `选项 ${node.branches.length + 1}`, next_node_id: '' }])
  }
  const removeBranch = (index: number) => {
    const branch = node.branches[index]
    if (branch.next_node_id && !window.confirm('确定删除该分支及其全部后续步骤？')) return
    onRemoveBranch(branch.id)
  }
  const moveBranch = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= node.branches.length) return
    const branches = [...node.branches]
    const [branch] = branches.splice(index, 1)
    branches.splice(target, 0, branch)
    update('branches', branches)
  }

  return (
    <div className="space-y-5 p-5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <span className="text-xs font-medium text-primary">{outboundScriptNodeLabel(node.type)}</span>
          <p className="mt-1 text-xs text-muted-foreground">已选中</p>
        </div>
        {node.type !== 'start' && (
          <button type="button" onClick={() => onDelete(node.id)} className="rounded-md p-2 text-destructive hover:bg-destructive/10" aria-label="删除步骤"><IconTrash size={17} /></button>
        )}
      </div>

      {node.type === 'start' ? (
        <AddNextStep disabled={Boolean(node.next_node_id)} onAdd={onAddChild} />
      ) : (
        <>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">步骤标题</span>
            <input value={node.title} maxLength={80} onChange={(event) => update('title', event.target.value)} className="h-10 rounded-md border border-border bg-background px-3 outline-none" />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">{node.type === 'end' ? '收尾话术' : '建议话术'}{node.type === 'script' && <span className="text-destructive"> *</span>}</span>
            <OutboundScriptRichText value={node.content} onChange={(value) => update('content', value)} placeholder="输入客服可直接表达的话术" />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">客服提示</span>
            <OutboundScriptRichText value={node.agent_tip} onChange={(value) => update('agent_tip', value)} placeholder="输入仅客服可见的提示" />
          </label>

          {node.type === 'branch' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between"><span className="text-sm font-medium">分支选项</span><button type="button" onClick={addBranch} disabled={node.branches.length >= 8} className="inline-flex items-center gap-1 text-xs text-primary disabled:opacity-40"><IconPlus size={14} />新增</button></div>
              {node.branches.map((branch, index) => (
                <div key={branch.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center gap-1">
                    <input value={branch.label} maxLength={40} onChange={(event) => update('branches', node.branches.map((item) => item.id === branch.id ? { ...item, label: event.target.value } : item))} className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm" />
                    <SmallButton label="上移" disabled={index === 0} onClick={() => moveBranch(index, -1)}><IconArrowUp size={14} /></SmallButton>
                    <SmallButton label="下移" disabled={index === node.branches.length - 1} onClick={() => moveBranch(index, 1)}><IconArrowDown size={14} /></SmallButton>
                    <SmallButton label="删除" disabled={node.branches.length <= 2} onClick={() => removeBranch(index)}><IconTrash size={14} /></SmallButton>
                  </div>
                  {!branch.next_node_id && <AddNextStep compact onAdd={(type) => onAddChild(type, branch.id)} />}
                </div>
              ))}
            </div>
          )}
          {node.type === 'script' && <AddNextStep disabled={Boolean(node.next_node_id)} onAdd={onAddChild} />}
        </>
      )}
    </div>
  )
}

function AddNextStep({ onAdd, disabled = false, compact = false }: { onAdd: (type: 'script' | 'branch' | 'end') => void; disabled?: boolean; compact?: boolean }) {
  if (disabled) return null
  return (
    <div className={compact ? 'mt-3' : 'space-y-2'}>
      {!compact && <p className="text-sm font-medium">添加后续步骤</p>}
      <div className="grid grid-cols-3 gap-2">
        {([['script', '话术'], ['branch', '分支'], ['end', '结束']] as const).map(([type, label]) => (
          <button key={type} type="button" onClick={() => onAdd(type)} className="rounded-md border border-border px-2 py-2 text-xs hover:bg-muted">{label}</button>
        ))}
      </div>
    </div>
  )
}

function SmallButton({ label, disabled, onClick, children }: { label: string; disabled?: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" title={label} aria-label={label} disabled={disabled} onClick={onClick} className="rounded p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-30">{children}</button>
}
