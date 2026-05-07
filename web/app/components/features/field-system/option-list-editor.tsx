'use client'

import { useState, useCallback } from 'react'
import { IconPlus, IconTrash, IconGripVertical } from '@tabler/icons-react'
import { RampColorPalette } from '@/components/ui/ramp-color-palette'
import { cn } from '@/lib/utils'

export type OptionItem = {
  label: string
  value: string
  color?: string | null
}

type OptionListEditorProps = {
  options: OptionItem[]
  onChange: (options: OptionItem[]) => void
  className?: string
}

/** Internal storage key for each option; auto-generated, not shown in UI. */
function nextAutoOptionValue(options: OptionItem[]): string {
  let max = 0
  for (const o of options) {
    const m = /^option_(\d+)$/.exec((o.value ?? '').trim())
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `option_${max + 1}`
}

export function OptionListEditor({ options, onChange, className }: OptionListEditorProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)

  const addOption = useCallback(() => {
    onChange([
      ...options,
      { label: '', value: nextAutoOptionValue(options), color: null },
    ])
  }, [options, onChange])

  const removeOption = useCallback(
    (index: number) => {
      onChange(options.filter((_, i) => i !== index))
    },
    [options, onChange],
  )

  const updateOption = useCallback(
    (index: number, field: keyof OptionItem, val: string | null) => {
      const updated = options.map((opt, i) => (i === index ? { ...opt, [field]: val } : opt))
      onChange(updated)
    },
    [options, onChange],
  )

  const handleDragStart = (index: number) => setDragIndex(index)
  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault()
    setDragOverIndex(index)
  }
  const handleDrop = (targetIndex: number) => {
    if (dragIndex === null || dragIndex === targetIndex) return
    const reordered = [...options]
    const [moved] = reordered.splice(dragIndex, 1)
    reordered.splice(targetIndex, 0, moved)
    onChange(reordered)
    setDragIndex(null)
    setDragOverIndex(null)
  }
  const handleDragEnd = () => {
    setDragIndex(null)
    setDragOverIndex(null)
  }

  return (
    <div className={cn('space-y-2', className)}>
      {options.map((opt, index) => (
        <div
          key={index}
          draggable
          onDragStart={() => handleDragStart(index)}
          onDragOver={(e) => handleDragOver(e, index)}
          onDrop={() => handleDrop(index)}
          onDragEnd={handleDragEnd}
          className={cn(
            'flex items-center gap-2 rounded-md border border-border px-2 py-1.5 transition-colors',
            dragOverIndex === index && 'border-primary/40 bg-muted/50',
          )}
        >
          <IconGripVertical size={16} className="shrink-0 cursor-grab text-muted-foreground" />

          {/* Color dot selector */}
          <ColorDot
            color={opt.color ?? null}
            onSelect={(c) => updateOption(index, 'color', c)}
          />

          <input
            type="text"
            value={opt.label}
            onChange={(e) => updateOption(index, 'label', e.target.value)}
            placeholder="选项名称"
            className="h-8 flex-1 rounded-md bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => removeOption(index)}
            className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <IconTrash size={16} />
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={addOption}
        className="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <IconPlus size={16} />
        添加选项
      </button>
    </div>
  )
}

function ColorDot({
  color,
  onSelect,
}: {
  color: string | null
  onSelect: (color: string | null) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    // Popover needs w-max: abspos width otherwise follows the ~24px trigger in the flex row.
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border transition-colors hover:border-muted-foreground"
      >
        {color ? (
          <span className="h-4 w-4 rounded-full" style={{ backgroundColor: color }} />
        ) : (
          <span className="h-4 w-4 rounded-full bg-muted" />
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-8 z-50 w-max rounded-lg border border-border bg-background p-2 shadow-md">
            <RampColorPalette
              selectedColor={color}
              onSelect={(c) => {
                onSelect(c)
                setOpen(false)
              }}
              onClear={() => {
                onSelect(null)
                setOpen(false)
              }}
            />
          </div>
        </>
      )}
    </div>
  )
}
