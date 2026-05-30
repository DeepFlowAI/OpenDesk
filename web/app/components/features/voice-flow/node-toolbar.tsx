'use client'
import {
  IconVolume,
  IconKeyboard,
  IconGitBranch,
  IconUserCheck,
  IconPhoneOff,
} from '@tabler/icons-react'
import type { NodeType } from '@/models/voice-flow-graph'
import { NODE_COLOR } from '@/models/voice-flow-graph'

export const NODE_DRAG_MIME = 'application/x-voice-flow-node-type'

const ITEMS: { type: NodeType; label: string; icon: React.ReactNode }[] = [
  { type: 'play', label: '纯语音', icon: <IconVolume size={16} /> },
  { type: 'collect', label: '收集输入', icon: <IconKeyboard size={16} /> },
  { type: 'condition', label: '信息判定', icon: <IconGitBranch size={16} /> },
  { type: 'assign_queue', label: '分配队列', icon: <IconUserCheck size={16} /> },
  { type: 'hangup', label: '挂断', icon: <IconPhoneOff size={16} /> },
]

export function NodeToolbar({ onAdd }: { onAdd: (type: NodeType) => void }) {
  const handleDragStart = (e: React.DragEvent<HTMLButtonElement>, type: NodeType) => {
    e.dataTransfer.setData(NODE_DRAG_MIME, type)
    e.dataTransfer.effectAllowed = 'copy'
  }
  return (
    <div className="rounded-xl border border-border bg-white px-3 py-2 shadow-md">
      <div className="flex items-center gap-2">
        {ITEMS.map((it) => (
          <button
            key={it.type}
            type="button"
            draggable
            onDragStart={(e) => handleDragStart(e, it.type)}
            onClick={() => onAdd(it.type)}
            title="点击新增 / 拖拽到画布定位"
            className="flex cursor-grab items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground/80 hover:bg-muted active:cursor-grabbing"
          >
            <span style={{ color: NODE_COLOR[it.type] }}>{it.icon}</span>
            {it.label}
          </button>
        ))}
      </div>
    </div>
  )
}
