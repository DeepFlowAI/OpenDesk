'use client'

import { useState } from 'react'
import { IconInfoCircle, IconPlayerPlay } from '@tabler/icons-react'

import { SafeHtml } from '@/components/safe-html'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import type { OutboundScript } from '@/models/outbound-task'
import { OutboundScriptCanvas } from './outbound-script-canvas'
import { OutboundScriptRunner } from './outbound-script-runner'
import { outboundScriptMaxDepth } from './outbound-script-utils'

export function OutboundScriptSnapshot({ script, templateName }: { script: OutboundScript | null | undefined; templateName: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(script?.nodes[0]?.id ?? null)
  const [previewOpen, setPreviewOpen] = useState(false)

  if (!script) {
    return <div className="rounded-lg border border-dashed border-border py-16 text-center"><h3 className="text-base font-semibold">该任务创建时未配置外呼话术</h3><p className="mt-2 text-sm text-muted-foreground">任务不会跟随模板之后新增的话术。</p></div>
  }
  const selected = script.nodes.find((node) => node.id === selectedId) ?? script.nodes[0]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-lg border border-info/20 bg-info/10 px-4 py-3 text-sm"><IconInfoCircle size={17} className="text-info" />这是任务创建时复制的话术。模板后续修改不会影响当前任务。</div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="来源模板" value={templateName} />
        <Stat label="节点数量" value={String(script.nodes.length)} />
        <Stat label="最大层级" value={String(outboundScriptMaxDepth(script))} />
      </div>
      <div className="flex justify-end"><button type="button" onClick={() => setPreviewOpen(true)} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"><IconPlayerPlay size={16} />预览运行</button></div>
      <div className="grid h-[520px] min-h-0 grid-cols-[minmax(0,1fr)_320px] overflow-hidden rounded-lg border border-border">
        <div className="min-h-0 bg-muted/30"><OutboundScriptCanvas script={script} selectedId={selected?.id ?? null} readOnly onSelect={setSelectedId} /></div>
        <aside className="overflow-auto border-l border-border p-5">
          {selected && <><p className="text-xs text-muted-foreground">只读步骤</p><h3 className="mt-2 text-base font-semibold">{selected.title}</h3>{selected.content && <SafeHtml html={selected.content} className={cn('mt-5 text-sm leading-6', richTextListStyleClass)} />}{selected.agent_tip && <div className="mt-4 rounded-lg bg-warning/10 p-3"><p className="mb-2 text-xs font-medium">客服提示</p><SafeHtml html={selected.agent_tip} className={cn('text-sm', richTextListStyleClass)} /></div>}{selected.type === 'branch' && <div className="mt-5 space-y-2">{selected.branches.map((branch) => <div key={branch.id} className="rounded-md border border-border px-3 py-2 text-sm">{branch.label}</div>)}</div>}</>}
        </aside>
      </div>
      <OutboundScriptRunner open={previewOpen} script={script} title="预览话术流程" subtitle={templateName} onClose={() => setPreviewOpen(false)} />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-lg border border-border p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 truncate text-lg font-semibold">{value}</p></div>
}
