'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { ReactFlowProvider } from '@xyflow/react'
import { toast } from 'sonner'
import { IconArrowLeft, IconDeviceFloppy, IconEdit, IconHistory, IconX } from '@tabler/icons-react'
import { Switch } from '@/components/ui/switch'
import { useUnifiedFields } from '@/service/use-field-definitions'
import {
  useTicketWorkflow,
  useUpdateTicketWorkflow,
} from '@/service/use-ticket-workflows'
import { TicketWorkflowCanvas, type InsertNodeType, type InsertTarget } from '@/app/components/features/ticket-workflow/canvas'
import { TicketWorkflowPropertyPanel } from '@/app/components/features/ticket-workflow/property-panel'
import { TicketWorkflowVersionsDrawer } from '@/app/components/features/ticket-workflow/versions-drawer'
import {
  appendBranch,
  defaultTicketWorkflowGraph,
  newBranchNode,
  newUpdateNode,
  type BranchNode,
  type TicketWorkflowEdge,
  type TicketWorkflowGraph,
  type TicketWorkflowNode,
} from '@/models/ticket-workflow-graph'
import type { UpdateTicketWorkflowPayload } from '@/models/ticket-workflow'

export default function TicketWorkflowEditorPage() {
  const params = useParams()
  const id = Number.parseInt(params.id as string, 10)
  if (Number.isNaN(id)) return <p className="text-sm text-destructive">无效的流程 ID</p>

  return (
    <ReactFlowProvider>
      <EditorBody id={id} />
    </ReactFlowProvider>
  )
}

function EditorBody({ id }: { id: number }) {
  const router = useRouter()
  const { data: workflow, isLoading, refetch } = useTicketWorkflow(id)
  const update = useUpdateTicketWorkflow()
  const { data: fieldsData } = useUnifiedFields({ domain: 'ticket', include_metadata: true })
  const fields = useMemo(() => (fieldsData?.items ?? []).filter((field) => field.status === 'active'), [fieldsData?.items])

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [graph, setGraph] = useState<TicketWorkflowGraph>(defaultTicketWorkflowGraph())
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [preview, setPreview] = useState<{ versionNo: number; graph: TicketWorkflowGraph } | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [metaOpen, setMetaOpen] = useState(false)
  const [metaDraft, setMetaDraft] = useState({ name: '', description: '' })

  useEffect(() => {
    if (!workflow) return
    setName(workflow.name)
    setDescription(workflow.description ?? '')
    setEnabled(workflow.enabled)
    setGraph(workflow.graph_json ?? defaultTicketWorkflowGraph())
    setSelectedNodeId(null)
    setSelectedBranchId(null)
  }, [workflow])

  const activeGraph = preview?.graph ?? graph
  const selectedNode = activeGraph.nodes.find((node) => node.id === selectedNodeId) ?? null

  const selectNode = (nodeId: string | null, branchId: string | null = null) => {
    setSelectedNodeId(nodeId)
    setSelectedBranchId(branchId)
  }

  const save = async () => {
    if (!workflow) return
    if (!name.trim()) {
      toast.error('请填写流程名称')
      return
    }
    setErrors([])
    try {
      const payload: UpdateTicketWorkflowPayload = {
        name: name.trim(),
        description: description.trim() || null,
        enabled,
      }
      const persistedGraph = workflow.graph_json ?? defaultTicketWorkflowGraph()
      if (!isSameGraph(graph, persistedGraph)) {
        payload.graph_json = graph
      }
      const saved = await update.mutateAsync({
        id,
        data: payload,
      })
      toast.success(`已保存（版本 v${saved.current_version_no ?? '?'}）`)
      await refetch()
    } catch (err) {
      const response = (err as { response?: Response }).response
      let body: unknown = null
      try {
        body = await response?.json()
      } catch {
        body = null
      }
      const nextErrors = parseErrors(body)
      setErrors(nextErrors)
      toast.error(nextErrors.length ? '保存失败，请检查节点配置' : '保存失败')
    }
  }

  const updateNode = (nextNode: TicketWorkflowNode) => {
    setGraph((prev) => reconcileBranchEdges({
      ...prev,
      nodes: prev.nodes.map((node) => node.id === nextNode.id ? nextNode : node),
    }, nextNode))
  }

  const insertOnEdge = (target: InsertTarget, type: InsertNodeType) => {
    const node = type === 'branch' ? newBranchNode() : newUpdateNode()
    setGraph((prev) => {
      if (target.kind === 'branch_merge') {
        return insertNodeOnBranchMergeTrunk(prev, target.branchId, target.targetId, node)
      }
      return insertNodeOnEdge(prev, target.edgeId, node)
    })
  }

  const addBranchToNode = (nodeId: string) => {
    setGraph((prev) => {
      const branchNode = prev.nodes.find((node): node is BranchNode => node.id === nodeId && node.type === 'branch')
      if (!branchNode) return prev
      const nextNode: BranchNode = { ...branchNode, data: appendBranch(branchNode.data) }
      return reconcileBranchEdges({
        ...prev,
        nodes: prev.nodes.map((node) => node.id === nodeId ? nextNode : node),
      }, nextNode)
    })
  }

  const removeBranchFromNode = (nodeId: string, branchId: string) => {
    setGraph((prev) => {
      const branchNode = prev.nodes.find((node): node is BranchNode => node.id === nodeId && node.type === 'branch')
      if (!branchNode) return prev
      const branch = branchNode.data.branches.find((item) => item.id === branchId)
      if (!branch || branch.is_default || branchNode.data.branches.filter((item) => !item.is_default).length <= 1) return prev
      const nextNode: BranchNode = {
        ...branchNode,
        data: {
          ...branchNode.data,
          branches: branchNode.data.branches.filter((item) => item.id !== branchId),
        },
      }
      return reconcileBranchEdges({
        ...prev,
        nodes: prev.nodes.map((node) => node.id === nodeId ? nextNode : node),
      }, nextNode)
    })
  }

  const deleteNode = (nodeId: string) => {
    const result = deleteNodeFromGraph(graph, nodeId)
    if (!result.ok) {
      toast.error(result.message)
      return
    }
    setGraph(result.graph)
    setSelectedNodeId((current) => current === nodeId ? null : current)
    setSelectedBranchId((current) => selectedNodeId === nodeId ? null : current)
  }

  const openMetaEditor = () => {
    setMetaDraft({ name, description })
    setMetaOpen(true)
  }

  if (isLoading || !workflow) return <p className="text-sm text-muted-foreground">加载中...</p>

  return (
    <div className="-m-8 flex h-[calc(100vh-3.5rem)] min-h-[720px] flex-col overflow-hidden bg-[#f4f4f5]">
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-[#e5e5e5] bg-white px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" onClick={() => router.push('/ticket-workflows')} className="text-[#9ca3af] hover:text-[#1a1a1a]" aria-label="返回列表">
            <IconArrowLeft size={20} />
          </button>
          <h1 className="truncate text-base font-semibold text-[#1a1a1a]">编辑：{name || '未命名流程'}</h1>
          <button type="button" onClick={openMetaEditor} className="text-[#666] hover:text-[#1a1a1a]" aria-label="编辑流程信息">
            <IconEdit size={18} />
          </button>
          {workflow.current_version_no && (
            <span className="rounded bg-[#f1f1f1] px-2 py-1 text-xs text-[#777]">v{workflow.current_version_no}</span>
          )}
          {preview && (
            <span className="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700">
              预览 v{preview.versionNo}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setVersionsOpen(true)} className="flex h-9 items-center gap-1 rounded-md border border-[#d9d9d9] bg-white px-3 text-sm text-[#333] hover:bg-[#f7f7f7]">
            <IconHistory size={15} />
            历史版本
          </button>
          <div className="flex items-center gap-2 px-1 text-sm font-medium text-[#1a1a1a]">
            启用
            <Switch checked={enabled} onCheckedChange={setEnabled} disabled={!!preview} />
          </div>
          {preview ? (
            <button type="button" onClick={() => setPreview(null)} className="h-9 rounded-md border border-[#d9d9d9] bg-white px-3 text-sm hover:bg-[#f7f7f7]">
              退出预览
            </button>
          ) : (
            <button type="button" onClick={save} disabled={update.isPending} className="flex h-10 items-center gap-1 rounded-md bg-[#1a1a1a] px-5 text-sm font-medium text-white hover:bg-black disabled:opacity-50">
              <IconDeviceFloppy size={15} />
              {update.isPending ? '保存中...' : '保存'}
            </button>
          )}
        </div>
      </div>

      {errors.length > 0 && (
        <div className="shrink-0 border-b border-destructive/20 bg-destructive/5 px-5 py-2 text-sm text-destructive">
          {errors.slice(0, 3).map((error) => <p key={error}>{error}</p>)}
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <div className="absolute inset-0">
          <TicketWorkflowCanvas
            graph={activeGraph}
            selectedNodeId={selectedNodeId}
            onSelect={preview ? () => undefined : selectNode}
            onInsertNode={preview ? undefined : insertOnEdge}
            onAddBranch={preview ? undefined : addBranchToNode}
            onRemoveBranch={preview ? undefined : removeBranchFromNode}
            onDeleteNode={preview ? undefined : deleteNode}
          />
        </div>
        {preview ? (
          <aside className="absolute right-6 top-6 w-[300px] rounded-lg border border-[#e5e5e5] bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-foreground">历史版本预览</p>
            <p className="mt-2 text-sm text-muted-foreground">预览态不可编辑。退出预览后回到当前草稿。</p>
          </aside>
        ) : selectedNode ? (
          <TicketWorkflowPropertyPanel
            node={selectedNode}
            selectedBranchId={selectedBranchId}
            fields={fields}
            onChange={updateNode}
            onClose={() => selectNode(null)}
          />
        ) : (
          <div className="pointer-events-none absolute left-1/2 top-8 -translate-x-1/2 rounded-full bg-white/80 px-4 py-2 text-xs text-[#8a8a8a] shadow-sm">
            点击节点编辑配置
          </div>
        )}
      </div>

      {metaOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35">
          <div className="w-[420px] rounded-lg bg-white shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-[#e5e5e5] px-5">
              <h2 className="text-base font-semibold text-[#1a1a1a]">编辑流程信息</h2>
              <button type="button" onClick={() => setMetaOpen(false)} className="text-[#777] hover:text-[#1a1a1a]" aria-label="关闭">
                <IconX size={18} />
              </button>
            </div>
            <div className="space-y-5 p-5">
              <label className="block space-y-2">
                <span className="text-sm font-medium text-[#333]">流程名称 <span className="text-destructive">*</span></span>
                <input
                  value={metaDraft.name}
                  onChange={(event) => setMetaDraft((prev) => ({ ...prev, name: event.target.value }))}
                  className="h-10 w-full rounded-md border border-[#d9d9d9] px-3 text-sm outline-none focus:border-[#1a1a1a]"
                />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium text-[#333]">备注描述</span>
                <textarea
                  value={metaDraft.description}
                  onChange={(event) => setMetaDraft((prev) => ({ ...prev, description: event.target.value }))}
                  className="h-24 w-full resize-none rounded-md border border-[#d9d9d9] px-3 py-2 text-sm outline-none focus:border-[#1a1a1a]"
                />
              </label>
            </div>
            <div className="flex h-16 items-center justify-end gap-3 border-t border-[#e5e5e5] px-5">
              <button type="button" onClick={() => setMetaOpen(false)} className="h-10 rounded-md border border-[#d9d9d9] px-5 text-sm text-[#333] hover:bg-[#f7f7f7]">
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  setName(metaDraft.name)
                  setDescription(metaDraft.description)
                  setMetaOpen(false)
                }}
                className="h-10 rounded-md bg-[#1a1a1a] px-5 text-sm font-medium text-white hover:bg-black"
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}

      {versionsOpen && (
        <TicketWorkflowVersionsDrawer
          workflowId={id}
          onClose={() => setVersionsOpen(false)}
          onPreview={(versionNo, previewGraph) => setPreview({ versionNo, graph: previewGraph })}
          onRollbackSuccess={() => {
            setPreview(null)
            refetch()
          }}
        />
      )}
    </div>
  )
}

function insertNodeOnEdge(graph: TicketWorkflowGraph, edgeId: string, node: TicketWorkflowNode): TicketWorkflowGraph {
  const targetEdge = graph.edges.find((edge) => edge.id === edgeId)
  if (!targetEdge) return graph
  return spliceNodeOnEdge(graph, targetEdge, node)
}

function insertNodeOnBranchMergeTrunk(
  graph: TicketWorkflowGraph,
  branchId: string,
  targetId: string,
  node: TicketWorkflowNode,
): TicketWorkflowGraph {
  const affected = graph.edges.filter((edge) => edge.source === branchId && edge.target === targetId)
  if (!affected.length) return graph
  const other = graph.edges.filter((edge) => !(edge.source === branchId && edge.target === targetId))
  const nextEdges: TicketWorkflowEdge[] = [...other]
  for (const edge of affected) {
    nextEdges.push({
      id: `edge-${edge.source}-${edge.source_handle}-${node.id}`,
      source: edge.source,
      target: node.id,
      source_handle: edge.source_handle,
    })
  }
  if (node.type === 'branch') {
    node.data.branches.forEach((branch) => {
      nextEdges.push({
        id: `edge-${node.id}-${branch.id}-${targetId}`,
        source: node.id,
        target: targetId,
        source_handle: branch.id,
      })
    })
  } else {
    nextEdges.push({
      id: `edge-${node.id}-next-${targetId}`,
      source: node.id,
      target: targetId,
      source_handle: 'next',
    })
  }
  return {
    ...graph,
    nodes: [...graph.nodes.filter((item) => item.id !== 'end'), node, ...graph.nodes.filter((item) => item.id === 'end')],
    edges: nextEdges,
  }
}

function spliceNodeOnEdge(
  graph: TicketWorkflowGraph,
  targetEdge: TicketWorkflowEdge,
  node: TicketWorkflowNode,
): TicketWorkflowGraph {
  const baseEdges = graph.edges.filter((edge) => edge.id !== targetEdge.id)
  const nextEdges: TicketWorkflowEdge[] = [
    ...baseEdges,
    {
      id: `edge-${targetEdge.source}-${targetEdge.source_handle}-${node.id}`,
      source: targetEdge.source,
      target: node.id,
      source_handle: targetEdge.source_handle,
    },
  ]
  if (node.type === 'branch') {
    node.data.branches.forEach((branch) => {
      nextEdges.push({ id: `edge-${node.id}-${branch.id}-${targetEdge.target}`, source: node.id, target: targetEdge.target, source_handle: branch.id })
    })
  } else {
    nextEdges.push({ id: `edge-${node.id}-next-${targetEdge.target}`, source: node.id, target: targetEdge.target, source_handle: 'next' })
  }
  return {
    ...graph,
    nodes: [...graph.nodes.filter((item) => item.id !== 'end'), node, ...graph.nodes.filter((item) => item.id === 'end')],
    edges: nextEdges,
  }
}

function deleteNodeFromGraph(graph: TicketWorkflowGraph, nodeId: string): { ok: true; graph: TicketWorkflowGraph } | { ok: false; message: string } {
  const node = graph.nodes.find((item) => item.id === nodeId)
  if (!node) return { ok: false, message: '节点不存在' }
  if (node.type === 'trigger' || node.type === 'end') return { ok: false, message: '触发和结束节点不能删除' }

  const incoming = graph.edges.filter((edge) => edge.target === nodeId)
  const outgoing = graph.edges.filter((edge) => edge.source === nodeId)
  const outgoingTargets = [...new Set(outgoing.map((edge) => edge.target))]
  if (outgoingTargets.length > 1) return { ok: false, message: '该节点后续分支不唯一，暂不能直接删除' }

  const target = outgoingTargets[0] ?? 'end'
  const remainingEdges = graph.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
  const reconnected = incoming
    .filter((edge) => edge.source !== target)
    .map((edge) => ({
      id: `edge-${edge.source}-${edge.source_handle}-${target}`,
      source: edge.source,
      target,
      source_handle: edge.source_handle,
    }))

  return {
    ok: true,
    graph: {
      ...graph,
      nodes: graph.nodes.filter((item) => item.id !== nodeId),
      edges: [...remainingEdges, ...reconnected],
    },
  }
}

function reconcileBranchEdges(graph: TicketWorkflowGraph, node: TicketWorkflowNode): TicketWorkflowGraph {
  if (node.type !== 'branch') return graph
  const branch = node as BranchNode
  const existing = graph.edges.filter((edge) => edge.source === branch.id)
  const incomingAndOther = graph.edges.filter((edge) => edge.source !== branch.id)
  const next = [...incomingAndOther]
  branch.data.branches.forEach((item) => {
    const found = existing.find((edge) => edge.source_handle === item.id)
    next.push(found ?? { id: `edge-${branch.id}-${item.id}-end`, source: branch.id, target: 'end', source_handle: item.id })
  })
  return { ...graph, edges: next }
}

function parseErrors(body: unknown): string[] {
  const details = (body as { details?: { errors?: Array<{ node_id?: string | null; message?: string }> } } | null)?.details
  return (details?.errors ?? [])
    .map((error) => error.node_id ? `${error.node_id}: ${error.message}` : error.message)
    .filter((message): message is string => !!message)
}

function isSameGraph(left: TicketWorkflowGraph, right: TicketWorkflowGraph): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}
