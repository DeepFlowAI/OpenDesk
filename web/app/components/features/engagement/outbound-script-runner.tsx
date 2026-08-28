'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconArrowLeft, IconGitBranch, IconListTree, IconRefresh, IconX } from '@tabler/icons-react'

import { SafeHtml } from '@/components/safe-html'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import type { OutboundScript, OutboundScriptNode } from '@/models/outbound-task'
import { appendOutboundScriptHistory, firstOutboundScriptNode, outboundScriptNodeMap } from './outbound-script-utils'
import { OutboundScriptTree } from './outbound-script-tree'

export function OutboundScriptRunner({
  open,
  script,
  title = '话术流程',
  subtitle,
  sessionKey = 'preview',
  variant = 'overlay',
  onClose,
}: {
  open: boolean
  script: OutboundScript
  title?: string
  subtitle?: string
  sessionKey?: string | number
  variant?: 'overlay' | 'panel'
  onClose: () => void
}) {
  const first = firstOutboundScriptNode(script)
  const map = useMemo(() => outboundScriptNodeMap(script), [script])
  const [history, setHistory] = useState<string[]>(first ? [first.id] : [])
  const [showAll, setShowAll] = useState(false)
  const [directoryId, setDirectoryId] = useState<string | null>(first?.id ?? null)

  useEffect(() => {
    const next = firstOutboundScriptNode(script)
    setHistory(next ? [next.id] : [])
    setDirectoryId(next?.id ?? null)
    setShowAll(false)
  }, [script, sessionKey])

  if (!open) return null
  const current = map.get(history.at(-1) ?? '') ?? first
  const directoryNode = map.get(directoryId ?? '') ?? current
  const goTo = (nodeId: string) => {
    if (!map.has(nodeId)) return
    setHistory((items) => [...items, nodeId])
    setDirectoryId(nodeId)
    setShowAll(false)
  }
  const chooseFromDirectory = (branchNodeId: string, targetNodeId: string) => {
    if (!map.has(targetNodeId)) return
    setHistory((items) => appendOutboundScriptHistory(items, branchNodeId, targetNodeId))
    setDirectoryId(targetNodeId)
    setShowAll(false)
  }
  const restart = () => {
    if (!window.confirm('确定重新开始话术流程？')) return
    setHistory(first ? [first.id] : [])
    setDirectoryId(first?.id ?? null)
    setShowAll(false)
  }

  return (
    <aside className={cn(
      'flex min-h-0 flex-col border-l border-border bg-background',
      variant === 'overlay' ? 'fixed inset-y-0 right-0 z-50 w-[min(520px,100vw)]' : 'h-full w-[520px] shrink-0',
    )} aria-label={title}>
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-border px-5">
        <div className="min-w-0"><h2 className="truncate text-base font-semibold">{showAll ? '全部话术' : title}</h2>{subtitle && <p className="truncate text-xs text-muted-foreground">{subtitle}</p>}</div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setShowAll((value) => !value)} className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted"><IconListTree size={16} />{showAll ? '逐步引导' : '查看全部'}</button>
          <button type="button" onClick={restart} className="rounded-md p-2 text-muted-foreground hover:bg-muted" title="重新开始" aria-label="重新开始"><IconRefresh size={16} /></button>
          <button type="button" onClick={onClose} className="rounded-md p-2 text-muted-foreground hover:bg-muted" title="关闭" aria-label="关闭"><IconX size={17} /></button>
        </div>
      </header>

      {showAll ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="max-h-[42%] shrink-0 overflow-auto border-b border-border py-2">
            <OutboundScriptTree script={script} selectedId={directoryNode?.id ?? null} invalidNodeIds={new Set()} onSelect={setDirectoryId} />
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-6">{directoryNode ? <AllScriptContent node={directoryNode} map={map} onChoose={(targetId) => chooseFromDirectory(directoryNode.id, targetId)} onNext={goTo} /> : <p className="text-sm text-muted-foreground">请选择话术步骤</p>}</div>
        </div>
      ) : current ? (
        <>
          <div className="min-h-0 flex-1 overflow-auto p-6">
            <div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-foreground font-semibold text-background">{history.length}</span><span>{current.type === 'branch' ? '情景分支' : current.type === 'end' ? '结束步骤' : '话术步骤'}</span></div>
            <h3 className="mt-3 font-display text-xl font-semibold">{current.title}</h3>
            {current.content && <section className="mt-6 rounded-xl border border-border p-4"><p className="mb-2 text-xs text-muted-foreground">{current.type === 'end' ? '收尾话术' : '建议话术'}</p><SafeHtml html={current.content} className={cn('text-base leading-7', richTextListStyleClass)} /></section>}
            {current.agent_tip && <section className="mt-4 rounded-xl border border-warning/40 bg-warning/10 p-4"><p className="mb-2 text-xs font-medium">客服提示</p><SafeHtml html={current.agent_tip} className={cn('text-sm leading-6', richTextListStyleClass)} /></section>}
            {current.type === 'end' ? <span className="mt-5 inline-flex rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">流程已结束</span> : current.type === 'branch' ? <BranchButtons node={current} map={map} onChoose={goTo} /> : current.next_node_id ? <button type="button" onClick={() => goTo(current.next_node_id as string)} className="mt-6 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground">下一步</button> : null}
          </div>
          <footer className="flex h-16 shrink-0 items-center justify-between border-t border-border px-5">
            <button type="button" disabled={history.length <= 1} onClick={() => setHistory((items) => items.slice(0, -1))} className="inline-flex items-center gap-1 text-sm text-muted-foreground disabled:opacity-30"><IconArrowLeft size={16} />上一步</button>
            {current.type === 'branch' && <span className="text-xs text-muted-foreground">选择客户的实际反馈</span>}
          </footer>
        </>
      ) : <div className="p-6 text-sm text-destructive">话术流程不可用</div>}
    </aside>
  )
}

function BranchButtons({ node, map, onChoose }: { node: OutboundScriptNode; map: Map<string, OutboundScriptNode>; onChoose: (nodeId: string) => void }) {
  return (
    <section className="mt-6">
      <p className="mb-3 flex items-center gap-1 text-sm font-medium"><IconGitBranch size={16} />客户反馈</p>
      <div className="grid grid-cols-2 gap-2">
        {node.branches.map((branch) => <button key={branch.id} type="button" onClick={() => onChoose(branch.next_node_id)} className="rounded-lg border border-border p-3 text-left hover:border-foreground hover:bg-muted"><span className="block text-sm font-medium">{branch.label}</span><span className="mt-1 block truncate text-xs text-muted-foreground">{map.get(branch.next_node_id)?.title ?? '未连接'}</span></button>)}
      </div>
    </section>
  )
}

function AllScriptContent({ node, map, onChoose, onNext }: { node: OutboundScriptNode; map: Map<string, OutboundScriptNode>; onChoose: (nodeId: string) => void; onNext: (nodeId: string) => void }) {
  return (
    <>
      <p className="text-xs text-muted-foreground">{node.type === 'branch' ? '情景分支' : node.type === 'end' ? '结束步骤' : '话术步骤'}</p>
      <h3 className="mt-2 text-lg font-semibold">{node.title}</h3>
      {node.content && <SafeHtml html={node.content} className={cn('mt-5 text-sm leading-6', richTextListStyleClass)} />}
      {node.agent_tip && <SafeHtml html={node.agent_tip} className={cn('mt-4 rounded-lg bg-warning/10 p-3 text-sm', richTextListStyleClass)} />}
      {node.type === 'end' ? (
        <span className="mt-5 inline-flex rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">流程已结束</span>
      ) : node.type === 'branch' ? (
        <BranchButtons node={node} map={map} onChoose={onChoose} />
      ) : node.next_node_id ? (
        <button type="button" onClick={() => onNext(node.next_node_id as string)} className="mt-6 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground">下一步</button>
      ) : null}
    </>
  )
}
