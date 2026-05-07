'use client'

import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import Tree from 'rc-tree'
import type { DataNode } from 'rc-tree/es/interface'
import 'rc-tree/assets/index.css'
import './tree-select-rc-overrides.css'
import { ChevronDown, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { FdTreeNode } from '@/models/field-definition'

type TreeMaps = {
  treeData: DataNode[]
  idToValue: Map<number, string>
  valueToId: Map<string, number>
}

function buildTreeMaps(all: FdTreeNode[], multi: boolean, leafOnly: boolean): TreeMaps {
  const idToValue = new Map<number, string>()
  const valueToId = new Map<string, number>()
  for (const n of all) {
    if (!n.is_active) continue
    idToValue.set(n.id, n.value)
    if (!valueToId.has(n.value)) valueToId.set(n.value, n.id)
  }

  const hasChild = (id: number) => all.some((c) => c.is_active && c.parent_id === id)

  function build(parentId: number | null): DataNode[] {
    const row = all
      .filter((n) => n.is_active && (parentId === null ? n.parent_id === null : n.parent_id === parentId))
      .sort((a, b) => a.sort_order - b.sort_order)

    return row.map((n) => {
      const isLeaf = !hasChild(n.id)
      const children = build(n.id)
      const node: DataNode = {
        key: String(n.id),
        title: n.label,
      }
      if (children.length > 0) node.children = children
      if (multi) {
        const onlyLeaves = leafOnly && !isLeaf
        node.disableCheckbox = onlyLeaves
        node.checkable = !onlyLeaves
      } else {
        node.selectable = leafOnly ? isLeaf : true
      }
      return node
    })
  }

  return { treeData: build(null), idToValue, valueToId }
}

function normalizeMultiValue(value: unknown): string[] {
  if (value == null) return []
  if (Array.isArray(value)) return (value as string[]).filter(Boolean)
  if (typeof value === 'string') return value.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  return []
}

function labelForTreeValue(value: string, nodes: FdTreeNode[]): string | null {
  const n = nodes.find((x) => x.is_active && x.value === value)
  return n?.label ?? null
}

function summarizeTriggerText(
  multi: boolean,
  value: unknown,
  nodes: FdTreeNode[],
  placeholder: string,
): string {
  if (multi) {
    const vals = normalizeMultiValue(value)
    if (vals.length === 0) return placeholder
    const labels = vals.map((v) => labelForTreeValue(v, nodes) ?? v)
    return labels.join('、')
  }
  const str = (value as string) ?? ''
  if (!str) return placeholder
  return labelForTreeValue(str, nodes) ?? str
}

function getDropdownPlacement(root: HTMLElement | null, expectedHeight = 320): 'top' | 'bottom' {
  if (!root || typeof window === 'undefined') return 'bottom'
  const rect = root.getBoundingClientRect()
  let boundaryTop = 0
  let boundaryBottom = window.innerHeight

  let parent = root.parentElement
  while (parent) {
    const style = window.getComputedStyle(parent)
    if (/(auto|scroll|hidden)/.test(style.overflowY)) {
      const parentRect = parent.getBoundingClientRect()
      boundaryTop = Math.max(boundaryTop, parentRect.top)
      boundaryBottom = Math.min(boundaryBottom, parentRect.bottom)
      break
    }
    parent = parent.parentElement
  }

  const spaceBelow = boundaryBottom - rect.bottom
  const spaceAbove = rect.top - boundaryTop
  return spaceBelow < expectedHeight && spaceAbove > spaceBelow ? 'top' : 'bottom'
}

/** Ant Design–style: small right-pointing triangle; rotate 90° when expanded. */
function AntTreeSwitcher({ expanded, isLeaf }: { expanded: boolean; isLeaf: boolean }) {
  if (isLeaf) return <span className="inline-block w-4 shrink-0" aria-hidden />
  return (
    <span className="inline-flex h-4 w-[18px] shrink-0 items-center justify-center" aria-hidden>
      <svg
        viewBox="0 0 8 8"
        className={cn(
          'size-2 text-[rgba(0,0,0,0.45)] transition-transform dark:text-foreground/55',
          expanded && 'rotate-90',
        )}
        fill="currentColor"
        aria-hidden
      >
        <path d="M0 0 L0 7 L5.5 3.5 Z" />
      </svg>
    </span>
  )
}

export type TreeSelectEditorProps = {
  value: unknown
  onChange: (v: unknown) => void
  treeNodes: FdTreeNode[]
  multi: boolean
  leafOnly: boolean
  maxSelections?: number
  placeholder: string
  disabled: boolean
  className?: string
  autoFocus?: boolean
}

/**
 * Tree single / multi select: combobox trigger + dropdown panel with rc-tree.
 */
export function TreeSelectEditor({
  value,
  onChange,
  treeNodes,
  multi,
  leafOnly,
  maxSelections,
  placeholder,
  disabled,
  className,
  autoFocus = false,
}: TreeSelectEditorProps) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom')
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)
  const activeNodes = useMemo(() => treeNodes.filter((n) => n.is_active), [treeNodes])
  const { treeData, idToValue, valueToId } = useMemo(
    () => buildTreeMaps(activeNodes, multi, leafOnly),
    [activeNodes, multi, leafOnly],
  )

  const rootExpandedKeys = useMemo(
    () => treeData.map((n) => String(n.key)),
    [treeData],
  )

  const triggerText = useMemo(
    () => summarizeTriggerText(multi, value, activeNodes, placeholder),
    [multi, value, activeNodes, placeholder],
  )

  const multiValues = useMemo(
    () => (multi ? normalizeMultiValue(value) : []),
    [multi, value],
  )

  const isPlaceholderDisplay = useMemo(() => {
    if (multi) return multiValues.length === 0
    return !((value as string) ?? '').trim()
  }, [multi, value, multiValues])

  const selectedKeys = useMemo(() => {
    if (multi) return []
    const str = (value as string) ?? ''
    if (!str) return []
    const id = valueToId.get(str)
    return id != null ? [String(id)] : []
  }, [multi, value, valueToId])

  const checkedKeys = useMemo(() => {
    if (!multi) return []
    const vals = normalizeMultiValue(value)
    return vals.map((v) => valueToId.get(v)).filter((id): id is number => id != null).map(String)
  }, [multi, value, valueToId])

  const close = useCallback(() => setOpen(false), [])

  const removeMultiValue = useCallback(
    (v: string) => {
      const next = multiValues.filter((x) => x !== v)
      onChange(next.length > 0 ? next : null)
    },
    [multiValues, onChange],
  )

  useEffect(() => {
    if (!autoFocus || disabled) return
    triggerRef.current?.focus()
    setPlacement(getDropdownPlacement(rootRef.current))
    setOpen(true)
  }, [autoFocus, disabled])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, close])

  useEffect(() => {
    if (!open) return
    const updatePlacement = () => setPlacement(getDropdownPlacement(rootRef.current))
    updatePlacement()
    window.addEventListener('resize', updatePlacement)
    window.addEventListener('scroll', updatePlacement, true)
    return () => {
      window.removeEventListener('resize', updatePlacement)
      window.removeEventListener('scroll', updatePlacement, true)
    }
  }, [open])

  const treeClassWrap = cn(
    'tree-select-rc-ant max-h-[min(320px,50vh)] overflow-auto px-1 py-1.5 text-sm',
    // Base layout
    '[&_.rc-tree]:bg-transparent',
    '[&_.rc-tree-treenode]:!my-px [&_.rc-tree-treenode]:!py-0.5',
    // Ant-like row hover (subtle grey)
    '[&_.rc-tree-node-content-wrapper]:!min-h-7 [&_.rc-tree-node-content-wrapper]:!rounded',
    '[&_.rc-tree-node-content-wrapper]:!px-1.5 [&_.rc-tree-node-content-wrapper]:!leading-7',
    '[&_.rc-tree-node-content-wrapper:hover]:bg-black/[0.04] dark:[&_.rc-tree-node-content-wrapper:hover]:bg-white/[0.06]',
    // Override rc-tree default selected (orange / box-shadow) → Ant #e6f7ff
    '[&_.rc-tree-node-selected]:!bg-[#e6f7ff] dark:[&_.rc-tree-node-selected]:!bg-sky-950/45',
    '[&_.rc-tree-node-selected]:!shadow-none [&_.rc-tree-node-selected]:!opacity-100',
    '[&_.rc-tree-node-selected_.rc-tree-title]:!font-normal',
    // Default rc-tree switcher uses a background sprite; remove so custom SVG shows cleanly
    '[&_.rc-tree-switcher]:!bg-none',
  )

  if (treeData.length === 0) {
    return (
      <p className={cn('rounded-md border border-border px-2 py-2 text-sm text-muted-foreground', className)}>
        {placeholder}
      </p>
    )
  }

  return (
    <div ref={rootRef} className={cn('relative w-full', className)}>
      {/* div + nested tag-remove buttons: avoid invalid <button> inside <button> */}
      <div
        ref={triggerRef}
        role="combobox"
        aria-haspopup="tree"
        aria-expanded={open}
        aria-disabled={disabled}
        tabIndex={disabled ? -1 : 0}
        onClick={() => {
          if (disabled) return
          if (!open) setPlacement(getDropdownPlacement(rootRef.current))
          setOpen((o) => !o)
        }}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            if (!open) setPlacement(getDropdownPlacement(rootRef.current))
            setOpen((o) => !o)
          }
        }}
        className={cn(
          'flex w-full min-h-8 cursor-pointer items-center justify-between gap-1.5 rounded-lg border border-input bg-transparent py-1.5 pr-2 pl-2.5 text-left text-sm transition-colors outline-none select-none',
          'focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
          'dark:bg-input/30 dark:hover:bg-input/50',
          disabled && 'pointer-events-none cursor-not-allowed opacity-50',
          multi && multiValues.length > 0 && 'h-auto',
          isPlaceholderDisplay && 'text-muted-foreground',
        )}
      >
        {multi && multiValues.length > 0 ? (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
            {multiValues.map((v) => (
              <span
                key={v}
                className="inline-flex max-w-full min-h-5 items-center gap-0.5 rounded border border-border/80 bg-muted/70 py-0.5 pr-0.5 pl-1.5 text-xs text-foreground"
              >
                <span className="min-w-0 flex-1 truncate" title={labelForTreeValue(v, activeNodes) ?? v}>
                  {labelForTreeValue(v, activeNodes) ?? v}
                </span>
                <button
                  type="button"
                  className="inline-flex shrink-0 cursor-pointer items-center justify-center rounded p-0.5 text-muted-foreground hover:bg-background/80 hover:text-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    e.preventDefault()
                    if (!disabled) removeMultiValue(v)
                  }}
                >
                  <X className="size-3" aria-hidden />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <span className="min-w-0 flex-1 truncate text-left leading-5">{triggerText}</span>
        )}
        <ChevronDown
          className={cn('size-4 shrink-0 self-center text-muted-foreground transition-transform', open && 'rotate-180')}
        />
      </div>

      {open && (
        <>
          <div className="fixed inset-0 z-40" aria-hidden onClick={close} />
          <div
            className={cn(
              'absolute left-0 right-0 z-50 rounded-lg border border-border bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10',
              placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1',
            )}
            onMouseDown={(event) => event.preventDefault()}
          >
            {(multi || (!multi && String(value ?? '').trim() !== '')) && (
              <div className="border-b border-border px-2 py-1.5">
                {!multi && String(value ?? '').trim() !== '' && (
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => {
                      onChange(null)
                      close()
                    }}
                  >
                    {placeholder}
                  </button>
                )}
                {multi && (
                  <span className="text-xs text-muted-foreground">{placeholder}</span>
                )}
              </div>
            )}
            <div className={treeClassWrap}>
              <Tree
                disabled={disabled}
                treeData={treeData}
                defaultExpandedKeys={rootExpandedKeys}
                showLine={false}
                showIcon={false}
                switcherIcon={({ expanded, isLeaf }) => <AntTreeSwitcher expanded={!!expanded} isLeaf={!!isLeaf} />}
                checkable={multi}
                checkStrictly
                selectable={!multi}
                multiple={false}
                selectedKeys={selectedKeys}
                checkedKeys={checkedKeys}
                onSelect={(keys) => {
                  if (disabled || multi) return
                  const k = keys[0]
                  if (k == null) {
                    onChange(null)
                    return
                  }
                  onChange(idToValue.get(Number(k)) ?? null)
                  close()
                }}
                onCheck={(keys) => {
                  if (disabled || !multi) return
                  const raw = keys && typeof keys === 'object' && 'checked' in keys ? keys.checked : keys
                  const keyArr = (Array.isArray(raw) ? raw : []).map(String)
                  const nextVals = keyArr
                    .map((k) => idToValue.get(Number(k)))
                    .filter((v): v is string => v != null)
                  if (maxSelections != null && nextVals.length > maxSelections) {
                    return
                  }
                  onChange(nextVals.length > 0 ? nextVals : null)
                }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
