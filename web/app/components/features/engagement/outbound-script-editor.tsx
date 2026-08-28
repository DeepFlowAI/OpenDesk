'use client'

import { useMemo, useState } from 'react'
import { IconAdjustments, IconAlertTriangle, IconArrowsMaximize, IconLayoutGrid, IconListTree, IconPlayerPlay, IconPlus, IconTrash, IconX } from '@tabler/icons-react'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type { OutboundScript, OutboundScriptNode, OutboundScriptNodeType } from '@/models/outbound-task'
import { OutboundScriptCanvas } from './outbound-script-canvas'
import { OutboundScriptProperties } from './outbound-script-properties'
import { OutboundScriptRunner } from './outbound-script-runner'
import { OutboundScriptTree } from './outbound-script-tree'
import {
  addOutboundScriptChild,
  createOutboundScript,
  deleteOutboundScriptSubtree,
  layoutOutboundScript,
  outboundScriptChildren,
  validateOutboundScript,
} from './outbound-script-utils'

export function OutboundScriptEditor({ value, templateName, existingTemplate, onChange }: {
  value: OutboundScript | null
  templateName: string
  existingTemplate: boolean
  onChange: (script: OutboundScript | null) => void
}) {
  const [selectedId, setSelectedId] = useState<string | null>(value?.nodes[0]?.id ?? null)
  const [fitRequest, setFitRequest] = useState(0)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [deleteNode, setDeleteNode] = useState<OutboundScriptNode | null>(null)
  const [clearOpen, setClearOpen] = useState(false)
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  const [propsDrawerOpen, setPropsDrawerOpen] = useState(false)
  const issues = useMemo(() => value ? validateOutboundScript(value) : [], [value])
  const invalidNodeIds = useMemo(() => new Set(issues.map((issue) => issue.nodeId).filter((id): id is string => Boolean(id))), [issues])
  const selected = value?.nodes.find((node) => node.id === selectedId) ?? value?.nodes[0] ?? null

  if (!value) {
    return <div className="flex h-full items-center justify-center p-8"><div className="max-w-sm text-center"><h2 className="text-lg font-semibold">暂未配置外呼话术</h2><p className="mt-2 text-sm text-muted-foreground">创建分支话术，帮助客服根据客户反馈逐步沟通</p><button type="button" onClick={() => { const next = createOutboundScript(); onChange(next); setSelectedId(next.nodes[0].id) }} className="mt-5 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"><IconPlus size={16} />开始配置</button></div></div>
  }

  const changeNode = (next: OutboundScriptNode) => onChange({ ...value, nodes: value.nodes.map((node) => node.id === next.id ? next : node) })
  const addChild = (type: Exclude<OutboundScriptNodeType, 'start'>, branchId?: string) => {
    if (!selected) return
    const result = addOutboundScriptChild(value, selected.id, type, branchId)
    onChange(result.script)
    setSelectedId(result.nodeId)
  }
  const confirmDelete = () => {
    if (!deleteNode) return
    const next = deleteOutboundScriptSubtree(value, deleteNode.id)
    onChange(next)
    setSelectedId(next.nodes[0]?.id ?? null)
    setDeleteNode(null)
  }
  const removeBranch = (branchId: string) => {
    if (!selected || selected.type !== 'branch') return
    const branch = selected.branches.find((item) => item.id === branchId)
    let next = branch?.next_node_id ? deleteOutboundScriptSubtree(value, branch.next_node_id) : value
    next = { ...next, nodes: next.nodes.map((node) => node.id === selected.id ? { ...node, branches: node.branches.filter((item) => item.id !== branchId) } : node) }
    onChange(next)
  }
  const affectedCount = deleteNode ? countDescendants(value, deleteNode.id) : 0

  const treePanel = (onSelectNode: (nodeId: string) => void) => (
    <>
      <div className="border-b border-border px-4 py-3"><h3 className="text-sm font-semibold">节点目录</h3><p className="mt-1 text-xs text-muted-foreground">{value.nodes.length} 个节点</p></div>
      <OutboundScriptTree script={value} selectedId={selectedId} invalidNodeIds={invalidNodeIds} onSelect={onSelectNode} />
    </>
  )
  const propertiesPanel = selected
    ? <OutboundScriptProperties node={selected} onChange={changeNode} onAddChild={addChild} onDelete={(nodeId) => setDeleteNode(value.nodes.find((node) => node.id === nodeId) ?? null)} onRemoveBranch={removeBranch} />
    : <p className="p-5 text-sm text-muted-foreground">请选择画布中的步骤</p>

  return (
    <div className="flex h-full min-h-0 flex-col">
      {existingTemplate && <div className="shrink-0 border-b border-info/20 bg-info/10 px-6 py-3 text-xs text-info">修改只影响之后新建的外呼任务，已创建任务继续使用原话术。</div>}
      {issues.length > 0 && <button type="button" onClick={() => issues[0]?.nodeId && setSelectedId(issues[0].nodeId)} className="flex shrink-0 items-center gap-2 border-b border-destructive/20 bg-destructive/5 px-5 py-2 text-left text-xs text-destructive"><IconAlertTriangle size={15} />{issues[0].message}{issues.length > 1 && `（另有 ${issues.length - 1} 项）`}</button>}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setTreeDrawerOpen(true)} className="rounded-md border border-border p-2 xl:hidden" title="节点目录" aria-label="节点目录"><IconListTree size={16} /></button>
          <button type="button" disabled={!selected || selected.type === 'end' || selected.type === 'branch' || Boolean(selected.next_node_id) || value.nodes.length >= 100} onClick={() => addChild('script')} className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-40"><IconPlus size={16} />新增话术</button>
          <button type="button" onClick={() => onChange(layoutOutboundScript(value))} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm"><IconLayoutGrid size={16} />自动整理</button>
          <button type="button" onClick={() => setFitRequest((value) => value + 1)} className="rounded-md border border-border p-2" title="适应画布" aria-label="适应画布"><IconArrowsMaximize size={16} /></button>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setPropsDrawerOpen(true)} className="rounded-md border border-border p-2 xl:hidden" title="步骤属性" aria-label="步骤属性"><IconAdjustments size={16} /></button>
          <button type="button" disabled={issues.length > 0} onClick={() => setPreviewOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm disabled:opacity-40"><IconPlayerPlay size={16} />预览运行</button>
          <button type="button" onClick={() => setClearOpen(true)} className="inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-destructive hover:bg-destructive/10"><IconTrash size={16} />清空流程</button>
        </div>
      </div>
      <div className="relative grid min-h-0 flex-1 xl:grid-cols-[260px_minmax(360px,1fr)_360px]">
        <aside className="hidden min-h-0 overflow-auto border-r border-border xl:block">{treePanel(setSelectedId)}</aside>
        <div className="min-h-0 bg-muted/30"><OutboundScriptCanvas script={value} selectedId={selectedId} invalidNodeIds={invalidNodeIds} fitRequest={fitRequest} onSelect={setSelectedId} onPositionChange={(nodeId, position) => onChange({ ...value, nodes: value.nodes.map((node) => node.id === nodeId ? { ...node, position } : node) })} /></div>
        <aside className="hidden min-h-0 overflow-auto border-l border-border xl:block">{selected ? propertiesPanel : null}</aside>
        {treeDrawerOpen && (
          <div className="absolute inset-y-0 left-0 z-10 flex w-72 flex-col border-r border-border bg-background xl:hidden">
            <div className="flex shrink-0 items-center justify-end border-b border-border px-2 py-1">
              <button type="button" onClick={() => setTreeDrawerOpen(false)} className="rounded-md p-2 text-muted-foreground hover:bg-muted" aria-label="关闭节点目录"><IconX size={16} /></button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">{treePanel((nodeId) => { setSelectedId(nodeId); setTreeDrawerOpen(false); setPropsDrawerOpen(true) })}</div>
          </div>
        )}
        {propsDrawerOpen && (
          <div className="absolute inset-y-0 right-0 z-10 flex w-80 flex-col border-l border-border bg-background xl:hidden">
            <div className="flex shrink-0 items-center justify-end border-b border-border px-2 py-1">
              <button type="button" onClick={() => setPropsDrawerOpen(false)} className="rounded-md p-2 text-muted-foreground hover:bg-muted" aria-label="关闭步骤属性"><IconX size={16} /></button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">{propertiesPanel}</div>
          </div>
        )}
      </div>
      <OutboundScriptRunner open={previewOpen} script={value} title="预览话术流程" subtitle={templateName} onClose={() => setPreviewOpen(false)} />
      <ConfirmDialog open={Boolean(deleteNode)} title="删除话术步骤" message="确定删除以下步骤及其后续分支？保存后不可恢复。" itemName={deleteNode ? `${deleteNode.title} · 将删除 ${affectedCount} 个步骤` : undefined} confirmLabel="确定删除" variant="destructive" onCancel={() => setDeleteNode(null)} onConfirm={confirmDelete} />
      <ConfirmDialog open={clearOpen} title="清空外呼话术" message="已创建任务中的话术快照不受影响。" itemName={`${templateName || '当前模板'} · 将清空 ${value.nodes.length} 个节点`} confirmLabel="确定清空" variant="destructive" onCancel={() => setClearOpen(false)} onConfirm={() => { onChange(null); setClearOpen(false) }} />
    </div>
  )
}

function countDescendants(script: OutboundScript, rootId: string): number {
  const map = new Map(script.nodes.map((node) => [node.id, node]))
  const visited = new Set<string>()
  const visit = (id: string) => { if (visited.has(id)) return; visited.add(id); const node = map.get(id); if (node) outboundScriptChildren(node).forEach(visit) }
  visit(rootId)
  return visited.size
}
