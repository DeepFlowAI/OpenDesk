'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ReactFlowProvider, useEdgesState, useNodesState, type Edge, type Node } from '@xyflow/react'
import { IconAdjustments, IconAlertTriangle, IconArrowLeft, IconHistory, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { SatisfactionCanvas, satisfactionEdgeStyle, satisfactionFromBackend, satisfactionToBackend } from '@/app/components/features/satisfaction-flow/canvas'
import { SatisfactionPropertyPanel } from '@/app/components/features/satisfaction-flow/property-panel'
import { SatisfactionSettingsDrawer } from '@/app/components/features/satisfaction-flow/settings-drawer'
import { SatisfactionToolbar } from '@/app/components/features/satisfaction-flow/toolbar'
import { SatisfactionVersionsDrawer } from '@/app/components/features/satisfaction-flow/versions-drawer'
import { FlowInfoPopover } from '@/app/components/features/voice-flow/flow-info-popover'
import type {
  SatisfactionFlowDraft,
  SatisfactionFlowSettings,
  SatisfactionFlowVersionDetail,
  SatisfactionNode,
  SatisfactionOption,
} from '@/models/satisfaction-flow'
import { useSatisfactionFlow, useSaveSatisfactionFlow } from '@/service/use-satisfaction-flows'

type SaveErrorBody = {
  details?: { errors?: Array<{ node_id?: string | null; message: string }> }
  detail?: Array<{ msg: string }>
}
type EditorIssue = { node_id?: string | null; message: string }

function defaultNode(type: SatisfactionNode['type'], position?: { x: number; y: number }, questions: Node[] = []): Node {
  const id = `${type}_${crypto.randomUUID()}`
  const data: Record<string, unknown> = type === 'play'
    ? { prompt: { kind: 'tts', text: '请输入客户听到的提示语。' } }
    : type === 'question'
      ? { name: `评价问题 ${questions.length + 1}`, required: true, prompt: { kind: 'auto_tts', text: '请根据提示按键评价。' }, barge_in_disabled: false, options: [{ id: `option_${crypto.randomUUID()}`, dtmf: '1', label: '不满意' }, { id: `option_${crypto.randomUUID()}`, dtmf: '2', label: '满意' }], timeout_seconds: 8, retry: { enabled: true, no_input: 1, no_match: 1, no_input_prompt: { kind: 'tts', text: '未收到您的输入，请重新选择。' }, no_match_prompt: { kind: 'tts', text: '输入无效，请按提示重新选择。' } } }
      : type === 'condition'
        ? { groups: [{ id: `group_${crypto.randomUUID()}`, name: '条件 1', logic: 'AND', conditions: [{ question_node_id: questions[0]?.id ?? '', operator: 'is_answered', option_id: null }] }] }
        : type === 'end'
          ? { pre_play: { kind: 'tts', text: '感谢您的评价，祝您生活愉快。' }, completion_type: 'completed' }
          : {}
  return { id, type, position: position ?? { x: 240 + Math.random() * 80, y: 180 + Math.random() * 100 }, data }
}

function snapshot(name: string, description: string, settings: SatisfactionFlowSettings, nodes: Node[], edges: Edge[]): string {
  return JSON.stringify({ name, description, settings, graph: satisfactionToBackend(nodes, edges) })
}

export function SatisfactionFlowEditor({ id }: { id: number }) {
  const router = useRouter()
  const query = useSatisfactionFlow(id)
  const save = useSaveSatisfactionFlow()
  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges] = useEdgesState<Edge>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [settings, setSettings] = useState<SatisfactionFlowSettings>({ auto_transfer: false, agent_invite: true, inbound: true, outbound: false })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [previewVersion, setPreviewVersion] = useState<number | null>(null)
  const [issues, setIssues] = useState<EditorIssue[]>([])
  const [saved, setSaved] = useState('')
  const hydrated = useRef<number | null>(null)
  const draftBeforePreview = useRef<{ nodes: Node[]; edges: Edge[]; name: string; description: string; settings: SatisfactionFlowSettings } | null>(null)

  useEffect(() => {
    const flow = query.data
    if (!flow || hydrated.current === flow.current_version_no) return
    hydrated.current = flow.current_version_no
    const converted = satisfactionFromBackend(flow.graph_json)
    setNodes(converted.nodes); setEdges(converted.edges); setName(flow.name); setDescription(flow.description ?? ''); setSettings(flow.settings)
    setSaved(snapshot(flow.name, flow.description ?? '', flow.settings, converted.nodes, converted.edges))
  }, [query.data, setEdges, setNodes])

  const current = useMemo(() => snapshot(name, description, settings, nodes, edges), [name, description, settings, nodes, edges])
  const dirty = current !== saved && previewVersion === null
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault() }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  if (query.isLoading || !query.data) return <div className="grid h-screen place-items-center text-sm text-muted-foreground">满意度流程加载中...</div>
  const selected = nodes.find((node) => node.id === selectedId) ?? null
  const targetOptions = nodes.map((node) => ({ id: node.id, type: node.type ?? '', label: node.type === 'question' ? String(node.data.name ?? node.id) : `${node.type} · ${node.id.slice(0, 8)}` }))
  const questions = nodes.filter((node) => node.type === 'question').map((node) => ({ id: node.id, name: String(node.data.name ?? '未命名问题'), options: (node.data.options as SatisfactionOption[] | undefined) ?? [] }))

  function leave() {
    if (dirty) setLeaveOpen(true)
    else router.push('/flow-studio/satisfaction-flows')
  }
  function connect(source: string, handle: string, target: string | null) {
    setEdges((currentEdges) => {
      const filtered = currentEdges.filter((edge) => !(edge.source === source && (edge.sourceHandle ?? 'next') === handle))
      const sourceType = nodes.find((node) => node.id === source)?.type
      return target ? [...filtered, { id: `edge_${crypto.randomUUID()}`, source, target, sourceHandle: handle, type: 'smoothstep', style: satisfactionEdgeStyle(sourceType, handle) }] : filtered
    })
  }
  function addNode(type: SatisfactionNode['type'], position?: { x: number; y: number }) {
    const node = defaultNode(type, position, nodes.filter((item) => item.type === 'question'))
    setNodes((currentNodes) => [...currentNodes, node]); setSelectedId(node.id)
  }
  async function handleSave() {
    const draft: SatisfactionFlowDraft = { name: name.trim(), description: description.trim() || null, settings, graph_json: satisfactionToBackend(nodes, edges) }
    if (!draft.name) { toast.error('请填写流程名称'); return }
    try {
      const result = await save.mutateAsync({ id, draft })
      setIssues([]); setSaved(snapshot(draft.name, draft.description ?? '', settings, nodes, edges)); hydrated.current = result.current_version_no
      toast.success(`满意度流程已保存，当前版本 V${result.current_version_no}`)
    } catch (error: unknown) {
      const response = (error as { response?: Response }).response
      let body: SaveErrorBody | null = null
      try { body = await response?.json() as SaveErrorBody } catch { body = null }
      const nextIssues: EditorIssue[] = body?.details?.errors ?? body?.detail?.map((item) => ({ message: item.msg })) ?? [{ message: '保存失败，请重试' }]
      setIssues(nextIssues); setSelectedId(nextIssues.find((item) => item.node_id)?.node_id ?? null); toast.error(`保存失败：${nextIssues.length} 个问题`)
    }
  }
  function preview(version: SatisfactionFlowVersionDetail) {
    if (previewVersion === null) draftBeforePreview.current = { nodes, edges, name, description, settings }
    const converted = satisfactionFromBackend(version.graph_json)
    setNodes(converted.nodes); setEdges(converted.edges); setName(version.name_snapshot); setDescription(version.description_snapshot ?? ''); setSettings(version.settings); setPreviewVersion(version.version_no); setVersionsOpen(false)
  }
  function exitPreview() {
    const draft = draftBeforePreview.current
    if (draft) { setNodes(draft.nodes); setEdges(draft.edges); setName(draft.name); setDescription(draft.description); setSettings(draft.settings) }
    draftBeforePreview.current = null; setPreviewVersion(null)
  }

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" onClick={leave} aria-label="返回满意度流程列表" className="flex items-center text-foreground/80 hover:text-foreground"><IconArrowLeft size={18} /></button>
          <h1 className="max-w-[420px] truncate text-base font-semibold">{name}</h1>
          <FlowInfoPopover name={name} description={description} onChange={({ name: nextName, description: nextDescription }) => { setName(nextName); setDescription(nextDescription) }} />
          {query.data.enabled && <span className="rounded-md bg-success/10 px-2 py-0.5 text-xs text-success">启用中 · V{query.data.current_version_no}</span>}
        </div>
        <div className="flex items-center gap-2"><button type="button" onClick={() => setSettingsOpen(true)} className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"><IconAdjustments size={14} />应用设置</button><button type="button" onClick={() => setVersionsOpen(true)} className="flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"><IconHistory size={14} />历史版本</button><button type="button" onClick={() => void handleSave()} disabled={!dirty || save.isPending || previewVersion !== null} className="h-9 rounded-md bg-black px-4 text-sm font-medium text-white disabled:opacity-40">{save.isPending ? '保存中...' : '保存'}</button></div>
      </header>
      {previewVersion !== null && <div className="flex items-center justify-center gap-3 bg-info/10 px-4 py-2 text-sm"><span>正在查看历史版本 V{previewVersion}</span><button type="button" onClick={exitPreview} className="underline">退出预览</button></div>}
      {issues.length > 0 && <div className="flex items-start gap-2 border-b border-destructive/30 bg-destructive/10 px-5 py-3 text-sm"><IconAlertTriangle size={17} className="mt-0.5 text-destructive" /><div className="flex-1"><p className="font-medium">请修复以下问题后再保存</p>{issues.slice(0, 4).map((issue, index) => <button key={`${issue.message}-${index}`} type="button" onClick={() => issue.node_id && setSelectedId(issue.node_id)} className="mt-1 block text-left text-xs text-muted-foreground hover:underline">{issue.message}</button>)}</div><button type="button" onClick={() => setIssues([])} aria-label="关闭校验提示"><IconX size={16} /></button></div>}
      <div className="flex min-h-0 flex-1">
        <div className={`relative min-w-0 flex-1 ${previewVersion !== null ? 'pointer-events-none opacity-80' : ''}`}><SatisfactionCanvas nodes={nodes} edges={edges} setNodes={setNodes} setEdges={setEdges} selectedId={selectedId} onSelect={setSelectedId} onDropNode={(type, position) => addNode(type, position)} />{previewVersion === null && <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center"><div className="pointer-events-auto"><SatisfactionToolbar onAdd={(type) => addNode(type)} /></div></div>}</div>
        <div className={previewVersion !== null ? 'pointer-events-none opacity-70' : ''}><SatisfactionPropertyPanel selected={selected} targets={targetOptions} questions={questions} edgeTarget={(source, handle) => edges.find((edge) => edge.source === source && (edge.sourceHandle ?? 'next') === handle)?.target ?? null} updateData={(nodeId, data) => setNodes((currentNodes) => currentNodes.map((node) => node.id === nodeId ? { ...node, data } : node))} connect={connect} remove={(nodeId) => { setNodes((currentNodes) => currentNodes.filter((node) => node.id !== nodeId)); setEdges((currentEdges) => currentEdges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)); setSelectedId(null) }} /></div>
      </div>
      <SatisfactionSettingsDrawer open={settingsOpen} value={settings} onClose={() => setSettingsOpen(false)} onApply={setSettings} />
      <SatisfactionVersionsDrawer flowId={id} open={versionsOpen} onClose={() => setVersionsOpen(false)} onPreview={preview} onRestored={() => { hydrated.current = null; void query.refetch(); setVersionsOpen(false) }} />
      <ConfirmDialog open={leaveOpen} title="离开满意度流程编辑器" message="当前修改尚未保存，确定离开？" confirmLabel="确定离开" onCancel={() => setLeaveOpen(false)} onConfirm={() => router.push('/flow-studio/satisfaction-flows')} />
    </div>
  )
}

export function SatisfactionFlowEditorPage({ id }: { id: number }) {
  return <ReactFlowProvider><SatisfactionFlowEditor id={id} /></ReactFlowProvider>
}
