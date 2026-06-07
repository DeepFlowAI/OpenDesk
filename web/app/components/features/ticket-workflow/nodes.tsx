'use client'

import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { IconBolt, IconDotsVertical, IconEdit, IconPlus } from '@tabler/icons-react'
import {
  BRANCH_ADD_WIDTH,
  BRANCH_CHIP_WIDTH,
  BRANCH_GAP_X,
  BRANCH_PADDING_X,
  branchColumnsWidth,
} from './branch-geometry'
import type { BranchData, TriggerData, UpdateRecordData } from '@/models/ticket-workflow-graph'

const TONES = {
  trigger: '#f45105',
  branch: '#fff4bf',
  update: '#0f8377',
  end: '#1a1a1a',
  line: '#d4d4d4',
}

type NodeActions = {
  onEditNode?: () => void
  onEditBranch?: (branchId: string) => void
  onDeleteNode?: () => void
}

function Card({
  selected,
  title,
  tone,
  icon,
  children,
  showTarget = true,
  titleColor = 'text-white',
  onEdit,
  onDelete,
}: {
  selected?: boolean
  title: string
  tone: string
  icon: React.ReactNode
  children?: React.ReactNode
  showTarget?: boolean
  titleColor?: string
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <div
      className="relative w-[280px] overflow-hidden rounded-lg bg-white"
      style={{
        boxShadow: selected
          ? `0 0 0 2px ${tone}, 0 14px 26px rgba(15,23,42,0.16)`
          : '0 10px 24px rgba(15,23,42,0.10)',
      }}
    >
      {showTarget && (
        <Handle type="target" position={Position.Top} style={{ background: TONES.line, borderColor: TONES.line }} />
      )}
      <div className={`flex h-[52px] items-center justify-between px-4 text-sm font-semibold ${titleColor}`} style={{ background: tone }}>
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <NodeActionMenu onEdit={onEdit} onDelete={onDelete} />
      </div>
      <div className="space-y-1 px-4 py-3 text-xs leading-5 text-[#333]">{children}</div>
    </div>
  )
}

const NODE_MENU_WIDTH = 132
const NODE_MENU_HEIGHT = 72
const NODE_MENU_GAP = 6

function NodeActionMenu({
  onEdit,
  onDelete,
}: {
  onEdit?: () => void
  onDelete?: () => void
}) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) {
      setCoords(null)
      return
    }
    const updatePosition = () => {
      const el = buttonRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      const openAbove = spaceBelow < NODE_MENU_HEIGHT + NODE_MENU_GAP && rect.top > NODE_MENU_HEIGHT + NODE_MENU_GAP
      setCoords({
        top: openAbove ? rect.top - NODE_MENU_HEIGHT - NODE_MENU_GAP : rect.bottom + NODE_MENU_GAP,
        left: Math.max(8, Math.min(window.innerWidth - NODE_MENU_WIDTH - 8, rect.right - NODE_MENU_WIDTH)),
      })
    }
    updatePosition()
    window.addEventListener('scroll', updatePosition, true)
    window.addEventListener('resize', updatePosition)
    return () => {
      window.removeEventListener('scroll', updatePosition, true)
      window.removeEventListener('resize', updatePosition)
    }
  }, [open])

  const pick = (action?: () => void) => {
    action?.()
    setOpen(false)
  }

  const menu = open && coords && typeof document !== 'undefined'
    ? createPortal(
        <>
          <button
            type="button"
            className="fixed inset-0 z-[100] cursor-default bg-transparent"
            aria-label="关闭节点菜单"
            onClick={() => setOpen(false)}
          />
          <div
            className="fixed z-[101] w-[132px] overflow-hidden rounded-lg border border-[#e5e5e5] bg-white py-1 shadow-lg"
            style={{ top: coords.top, left: coords.left }}
          >
            <button
              type="button"
              onClick={() => pick(onEdit)}
              className="flex h-8 w-full items-center px-3 text-left text-xs font-normal text-[#404040] hover:bg-[#f5f5f5]"
            >
              编辑
            </button>
            {onDelete && (
              <button
                type="button"
                onClick={() => pick(onDelete)}
                className="flex h-8 w-full items-center px-3 text-left text-xs font-normal text-[#ef4444] hover:bg-[#fff1f1]"
              >
                删除
              </button>
            )}
          </div>
        </>,
        document.body,
      )
    : null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((prev) => !prev)
        }}
        className="nodrag nopan -mr-1 flex h-7 w-7 items-center justify-center rounded text-current/80 transition hover:bg-black/5 hover:text-current"
        aria-label="打开节点菜单"
      >
        <IconDotsVertical size={18} />
      </button>
      {menu}
    </>
  )
}

export function TriggerNodeView({ data, selected }: NodeProps) {
  const trigger = data as TriggerData & NodeActions
  const events = trigger.event_types.includes('create') && trigger.event_types.includes('update')
    ? '新建 · 编辑 生效'
    : trigger.event_types.includes('create')
      ? '新建 生效'
      : '编辑 生效'
  return (
    <Card
      selected={selected}
      title="触发"
      tone={TONES.trigger}
      icon={<IconBolt size={18} />}
      showTarget={false}
      onEdit={trigger.onEditNode}
    >
      <p className="text-[#666]">{events}</p>
      <p className="font-medium text-[#1a1a1a]">{trigger.conditions.length ? `条件：${trigger.conditions.length} 条` : '条件：无入口条件'}</p>
      <Handle type="source" position={Position.Bottom} id="next" style={{ background: TONES.line, borderColor: TONES.line }} />
    </Card>
  )
}

export function BranchNodeView({ data, selected }: NodeProps) {
  const branch = data as BranchData & NodeActions & {
    onAddBranch?: () => void
    columnSlots?: number[] | null
  }
  const columnSlots = branch.branches.map((_, index) => branch.columnSlots?.[index] ?? BRANCH_CHIP_WIDTH)
  const columnsWidth = columnSlots.length
    ? columnSlots.reduce((sum, width) => sum + width, 0) + Math.max(0, columnSlots.length - 1) * BRANCH_GAP_X
    : branchColumnsWidth(0)
  const outerWidth = columnsWidth + BRANCH_ADD_WIDTH + BRANCH_GAP_X + 2 * BRANCH_PADDING_X
  const mergeHandleLeft = `${((BRANCH_PADDING_X + columnsWidth / 2) / outerWidth) * 100}%`

  return (
    <div
      className="pointer-events-none relative flex items-start gap-3 rounded-xl px-1 py-1 pb-12"
      style={{
        boxShadow: selected ? '0 0 0 2px #1a1a1a22' : 'none',
      }}
    >
      <Handle
        type="target"
        id="__merge_in__"
        position={Position.Top}
        className="!pointer-events-auto"
        style={{ left: mergeHandleLeft, opacity: 0, width: 8, height: 8, background: TONES.line, borderColor: TONES.line }}
      />
      {branch.branches.map((item, index) => (
        <div
          key={item.id}
          className="pointer-events-none flex shrink-0 justify-center"
          style={{ width: columnSlots[index] }}
        >
          <div
            className="pointer-events-auto relative w-[134px] overflow-hidden rounded-lg bg-white shadow-sm"
            onClick={(event) => {
              event.stopPropagation()
              branch.onEditBranch?.(item.id)
            }}
          >
            <Handle
              type="target"
              position={Position.Top}
              id={`in-${item.id}`}
              className="!pointer-events-auto"
              style={{ left: '50%', background: TONES.line, borderColor: TONES.line }}
            />
            <div className={`flex h-9 items-center justify-between px-3 text-sm font-semibold ${item.is_default ? 'bg-[#fff4bf] text-[#9a5b00]' : 'bg-white text-[#1a1a1a]'}`}>
              <span className="truncate">{item.is_default ? '否则' : item.name}</span>
              <NodeActionMenu
                onEdit={() => branch.onEditBranch?.(item.id)}
                onDelete={branch.onDeleteNode}
              />
            </div>
            <div className="min-h-9 border-t border-[#eeeeee] px-3 py-2 text-xs text-[#555]">
              {item.is_default ? '默认分支' : item.conditions.length ? `${item.conditions.length} 条条件` : '未设置条件'}
            </div>
            <Handle
              type="source"
              position={Position.Bottom}
              id={item.id}
              className="!pointer-events-auto"
              style={{ left: '50%', background: TONES.line, borderColor: TONES.line }}
            />
          </div>
        </div>
      ))}
      <button
        type="button"
        disabled={!branch.onAddBranch}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation()
          branch.onAddBranch?.()
        }}
        className="nodrag nopan pointer-events-auto flex h-[73px] w-[132px] flex-col items-center justify-center rounded-lg border border-[#d9d9d9] bg-[#f5f5f5] text-xs text-[#777] transition hover:border-[#1a1a1a] hover:text-[#1a1a1a] disabled:cursor-default disabled:hover:border-[#d9d9d9] disabled:hover:text-[#777]"
      >
        <IconPlus size={16} className="mb-1 text-[#555]" />
        添加分支
      </button>
      <Handle
        type="source"
        id="__merge__"
        position={Position.Bottom}
        className="!pointer-events-auto"
        style={{ left: mergeHandleLeft, opacity: 0, width: 8, height: 8, background: TONES.line, borderColor: TONES.line }}
      />
    </div>
  )
}

export function UpdateRecordNodeView({ data, selected }: NodeProps) {
  const update = data as UpdateRecordData & NodeActions
  return (
    <Card
      selected={selected}
      title="更新记录"
      tone={TONES.update}
      icon={<IconEdit size={18} />}
      onEdit={update.onEditNode}
      onDelete={update.onDeleteNode}
    >
      <p className="font-medium text-[#1a1a1a]">修改 {update.operations.length} 个字段</p>
      <p className="text-[#666]">{update.operations[0]?.action === 'clear' ? '清空字段' : '设置字段值'}</p>
      <Handle type="source" position={Position.Bottom} id="next" style={{ background: TONES.line, borderColor: TONES.line }} />
    </Card>
  )
}

export function EndNodeView({ selected }: NodeProps) {
  return (
    <div className="relative flex w-[96px] flex-col items-center gap-2">
      <Handle type="target" position={Position.Top} style={{ background: TONES.line, borderColor: TONES.line }} />
      <div
        className="h-10 w-10 rounded-md bg-[#1a1a1a]"
        style={{ boxShadow: selected ? '0 0 0 2px #1a1a1a44' : 'none' }}
      />
      <p className="text-xs text-[#777]">流程结束</p>
    </div>
  )
}

export const TICKET_WORKFLOW_NODE_TYPES = {
  trigger: TriggerNodeView,
  branch: BranchNodeView,
  update_record: UpdateRecordNodeView,
  end: EndNodeView,
}
