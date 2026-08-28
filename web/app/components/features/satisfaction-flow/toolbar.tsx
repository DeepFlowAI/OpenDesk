'use client'

import { IconGitBranch, IconSquareRoundedCheck, IconStar, IconVolume } from '@tabler/icons-react'
import type { SatisfactionNode } from '@/models/satisfaction-flow'
import { SATISFACTION_NODE_COLOR } from '@/app/components/features/satisfaction-flow/nodes'

export const SATISFACTION_NODE_MIME = 'application/x-satisfaction-flow-node'

const ITEMS: Array<{ type: SatisfactionNode['type']; label: string; icon: React.ReactNode }> = [
  { type: 'play', label: '播放提示', icon: <IconVolume size={16} /> },
  { type: 'question', label: '评价问题', icon: <IconStar size={16} /> },
  { type: 'condition', label: '条件判断', icon: <IconGitBranch size={16} /> },
  { type: 'end', label: '结束', icon: <IconSquareRoundedCheck size={16} /> },
]

export function SatisfactionToolbar({ onAdd }: { onAdd: (type: SatisfactionNode['type']) => void }) {
  return (
    <div className="rounded-xl border border-border bg-white px-3 py-2 shadow-md">
      <div className="flex items-center gap-2">
        {ITEMS.map((item) => (
          <button
            key={item.type}
            type="button"
            draggable
            onDragStart={(event) => {
              event.dataTransfer.setData(SATISFACTION_NODE_MIME, item.type)
              event.dataTransfer.effectAllowed = 'copy'
            }}
            onClick={() => onAdd(item.type)}
            title="点击新增 / 拖拽到画布定位"
            className="flex cursor-grab items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground/80 hover:bg-muted active:cursor-grabbing"
          >
            <span style={{ color: SATISFACTION_NODE_COLOR[item.type] }}>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}
