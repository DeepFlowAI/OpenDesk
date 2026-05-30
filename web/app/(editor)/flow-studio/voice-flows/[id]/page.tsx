'use client'
/**
 * Voice flow editor — full ReactFlow canvas + property panel + top bar.
 *
 * Loads voice_flow + graph_json, lets the user edit nodes/edges/properties,
 * and saves the full graph back to PUT /voice-flows/{id} which bumps version.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconAlertTriangle,
  IconHistory,
  IconBraces,
  IconX,
} from '@tabler/icons-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from '@xyflow/react'
import { toast } from 'sonner'

import {
  VoiceFlowCanvas,
  fromBackend,
  makeNewNode,
  toBackend,
} from '@/app/components/features/voice-flow/canvas'
import { NodeToolbar } from '@/app/components/features/voice-flow/node-toolbar'
import { PropertyPanel } from '@/app/components/features/voice-flow/property-panel'
import { FlowInfoPopover } from '@/app/components/features/voice-flow/flow-info-popover'
import { VariablesModal } from '@/app/components/features/voice-flow/variables-modal'
import { VersionsDrawer } from '@/app/components/features/voice-flow/versions-drawer'
import { defaultDataFor, type NodeType } from '@/models/voice-flow-graph'
import { useUpdateVoiceFlow, useVoiceFlow } from '@/service/use-voice-flows'
import {
  formatIssueHeadline,
  parseValidationErrors,
  type ValidationIssue,
} from '@/utils/voice-flow-errors'
import { leaveVoiceFlowEditor } from '@/utils/voice-flow-editor-navigation'

export default function EditVoiceFlowPage() {
  const params = useParams()
  const raw = params.id as string
  const id = Number.parseInt(raw, 10)

  if (Number.isNaN(id)) {
    return <p className="p-6 text-sm text-red-600">无效的语音流程 ID</p>
  }
  return (
    <ReactFlowProvider>
      <EditorBody id={id} />
    </ReactFlowProvider>
  )
}

function EditorBody({ id }: { id: number }) {
  const router = useRouter()
  const { data: flow, isLoading, refetch } = useVoiceFlow(id)
  const update = useUpdateVoiceFlow()

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [variablesOpen, setVariablesOpen] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [previewVersion, setPreviewVersion] = useState<number | null>(null)
  const [savedSnapshot, setSavedSnapshot] = useState<string>('')
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([])
  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false)

  // Track which version we've hydrated so a window-focus refetch can't
  // silently overwrite the user's in-progress edits. We only re-hydrate
  // when the active version changes (save / rollback / explicit refetch).
  const hydratedVersionRef = useRef<number | null>(null)

  useEffect(() => {
    if (!flow) return
    const currentVer = flow.current_version_no ?? null
    if (hydratedVersionRef.current === currentVer) return
    hydratedVersionRef.current = currentVer
    const graph = flow.graph_json ?? { version: 1, nodes: [], edges: [], variables: [] }
    const { nodes: n, edges: e } = fromBackend(graph)
    setNodes(n)
    setEdges(e)
    setName(flow.name)
    setDescription(flow.description ?? '')
    setSavedSnapshot(snap(flow.name, flow.description ?? '', n, e))
  }, [flow, setNodes, setEdges])

  const currentSnap = useMemo(() => snap(name, description, nodes, edges), [name, description, nodes, edges])
  const isDirty = currentSnap !== savedSnapshot

  const handleLeave = () => {
    if (isDirty) {
      setLeaveConfirmOpen(true)
      return
    }
    leaveVoiceFlowEditor(router)
  }

  const updateNode = (nodeId: string, patch: { data?: Record<string, unknown> }) => {
    setNodes((prev) =>
      prev.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...(patch.data ?? {}) } } : n)),
    )
  }

  const addNode = (type: NodeType) => {
    const n = makeNewNode(type)
    setNodes((prev) => [...prev, n])
    setSelectedId(n.id)
  }

  const addNodeAt = (type: NodeType, position: { x: number; y: number }) => {
    const n = makeNewNode(type, position)
    setNodes((prev) => [...prev, n])
    setSelectedId(n.id)
  }

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请填写流程名称')
      return
    }
    setValidationIssues([])
    try {
      const graph = toBackend(nodes, edges)
      const updated = await update.mutateAsync({
        id,
        data: { name: name.trim(), description: description.trim() || null, graph_json: graph },
      })
      toast.success(`已保存（版本 ${updated.current_version_no ?? '?'}）`)
      setSavedSnapshot(snap(name, description, nodes, edges))
      refetch()
    } catch (err: unknown) {
      const httpErr = err as { response?: Response }
      let body: unknown = null
      try {
        body = await httpErr.response?.json?.()
      } catch {
        body = null
      }
      const issues = parseValidationErrors(body, nodes)
      if (issues.length) {
        setValidationIssues(issues)
        const firstNodeId = issues.find((i) => i.nodeId)?.nodeId
        if (firstNodeId) setSelectedId(firstNodeId)
        toast.error(`保存失败：共 ${issues.length} 个问题，请按提示修复`)
      } else {
        toast.error('保存失败：未知错误')
      }
    }
  }

  if (isLoading || !flow) {
    return <p className="p-6 text-sm text-muted-foreground">加载中...</p>
  }

  const selected = nodes.find((n) => n.id === selectedId) ?? null
  const flowVariables: { name: string; source_node_id: string }[] = nodes
    .filter((n) => n.type === 'collect')
    .map((n) => ({ name: (n.data as { output_variable?: string }).output_variable ?? '', source_node_id: n.id }))
    .filter((v) => v.name)

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleLeave}
            className="flex items-center gap-1 text-foreground/80 hover:text-foreground"
          >
            <IconArrowLeft size={18} />
          </button>
          <span className="text-base font-semibold">{name || '未命名语音流程'}</span>
          <FlowInfoPopover
            name={name}
            description={description}
            onChange={({ name: n, description: d }) => {
              setName(n)
              setDescription(d)
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setVariablesOpen(true)}
            className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            <IconBraces size={14} /> 变量
          </button>
          <button
            type="button"
            onClick={() => setVersionsOpen(true)}
            className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
          >
            <IconHistory size={14} /> 历史版本
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={update.isPending || !isDirty}
            className="h-9 rounded-md bg-black px-4 text-sm font-medium text-white disabled:opacity-40"
          >
            {update.isPending ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {validationIssues.length > 0 && (
        <ValidationBanner
          issues={validationIssues}
          nodes={nodes}
          onJumpTo={(nodeId) => setSelectedId(nodeId)}
          onDismiss={() => setValidationIssues([])}
        />
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="relative min-w-0 flex-1">
          <VoiceFlowCanvas
            nodes={nodes}
            edges={edges}
            setNodes={(updater) => {
              if (typeof updater === 'function') {
                setNodes(updater as (prev: Node[]) => Node[])
              } else {
                setNodes(updater)
              }
              void onNodesChange
            }}
            setEdges={(updater) => {
              if (typeof updater === 'function') {
                setEdges(updater as (prev: Edge[]) => Edge[])
              } else {
                setEdges(updater)
              }
              void onEdgesChange
            }}
            selectedNodeId={selectedId}
            onSelect={setSelectedId}
            onDropNode={addNodeAt}
          />
          <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
            <div className="pointer-events-auto">
              <NodeToolbar onAdd={addNode} />
            </div>
          </div>
        </div>

        <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-l border-border bg-white">
          <PropertyPanel
            selected={selected}
            updateNode={updateNode}
            allNodes={nodes.map((n) => ({ id: n.id, type: n.type ?? '', label: `${n.type} #${n.id}` }))}
            graphVariables={flowVariables.map((v) => v.name)}
          />
        </aside>
      </div>

      {variablesOpen && (
        <VariablesModal flowVariables={flowVariables} onClose={() => setVariablesOpen(false)} />
      )}

      {versionsOpen && (
        <VersionsDrawer
          flowId={id}
          onClose={() => setVersionsOpen(false)}
          onPreview={(versionNo, graph) => {
            const { nodes: n, edges: e } = fromBackend(graph)
            setNodes(n)
            setEdges(e)
            setPreviewVersion(versionNo)
            setVersionsOpen(false)
            toast.info(`预览版本 v${versionNo}（只读，未保存）`)
          }}
          onRollbackSuccess={() => refetch()}
        />
      )}

      <ConfirmDialog
        open={leaveConfirmOpen}
        title="放弃未保存的更改"
        message="当前画布有未保存的修改，离开后将丢失。"
        confirmLabel="放弃并离开"
        cancelLabel="继续编辑"
        variant="destructive"
        onCancel={() => setLeaveConfirmOpen(false)}
        onConfirm={() => {
          setLeaveConfirmOpen(false)
          leaveVoiceFlowEditor(router)
        }}
      />

      {previewVersion !== null && (
        <div className="fixed bottom-6 left-1/2 z-30 -translate-x-1/2 rounded-full bg-black/90 px-4 py-2 text-sm text-white shadow-lg">
          预览版本 v{previewVersion} · 未编辑
          <button
            type="button"
            onClick={() => {
              setPreviewVersion(null)
              if (flow) {
                const g = flow.graph_json ?? { version: 1, nodes: [], edges: [], variables: [] }
                const { nodes: n2, edges: e2 } = fromBackend(g)
                setNodes(n2)
                setEdges(e2)
                hydratedVersionRef.current = flow.current_version_no ?? null
              }
              refetch()
            }}
            className="ml-3 underline"
          >
            退出预览
          </button>
        </div>
      )}
    </div>
  )
}


function snap(name: string, desc: string, nodes: Node[], edges: Edge[]): string {
  return JSON.stringify({
    name: name.trim(),
    desc: desc.trim(),
    nodes: nodes.map((n) => ({ id: n.id, type: n.type, pos: n.position, data: n.data })),
    edges: edges.map((e) => ({ id: e.id, s: e.source, t: e.target, h: e.sourceHandle })),
  })
}

void defaultDataFor


function ValidationBanner({
  issues,
  nodes,
  onJumpTo,
  onDismiss,
}: {
  issues: ValidationIssue[]
  nodes: Node[]
  onJumpTo: (nodeId: string) => void
  onDismiss: () => void
}) {
  return (
    <div className="shrink-0 border-b border-red-200 bg-red-50">
      <div className="flex items-start gap-3 px-6 py-3">
        <IconAlertTriangle size={18} className="mt-0.5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-red-800">
            保存失败 · 检测到 {issues.length} 个配置问题
          </p>
          <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto pr-2 text-xs text-red-700">
            {issues.map((iss, idx) => (
              <li key={idx} className="flex items-start gap-1">
                <span className="text-red-400">•</span>
                {iss.nodeId ? (
                  <button
                    type="button"
                    onClick={() => onJumpTo(iss.nodeId!)}
                    className="text-left hover:underline"
                  >
                    {formatIssueHeadline(iss, nodes)}
                  </button>
                ) : (
                  <span>{formatIssueHeadline(iss, nodes)}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded p-1 text-red-600 hover:bg-red-100"
          aria-label="关闭"
        >
          <IconX size={16} />
        </button>
      </div>
    </div>
  )
}
