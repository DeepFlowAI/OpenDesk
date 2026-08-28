'use client'

import { IconPlus, IconTrash } from '@tabler/icons-react'

type EmbeddedCallOriginFieldsProps = {
  values: string[]
  disabled?: boolean
  isZh: boolean
  onChange: (values: string[]) => void
}

export function EmbeddedCallOriginFields({
  values,
  disabled,
  isZh,
  onChange,
}: EmbeddedCallOriginFieldsProps) {
  const update = (index: number, value: string) => {
    onChange(values.map((item, itemIndex) => (itemIndex === index ? value : item)))
  }

  return (
    <div className="flex flex-col gap-2">
      {values.map((value, index) => (
        <div key={index} className="flex items-center gap-2">
          <input
            value={value}
            disabled={disabled}
            placeholder="https://crm.example.com"
            className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-white px-3.5 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
            aria-label={isZh ? `允许来源 ${index + 1}` : `Allowed origin ${index + 1}`}
            onChange={(event) => update(index, event.target.value)}
            onBlur={() => {
              const normalized = value.trim().replace(/\/+$/, '')
              if (normalized !== value) update(index, normalized)
            }}
          />
          <button
            type="button"
            disabled={disabled || values.length === 1}
            aria-label={isZh ? '移除来源' : 'Remove origin'}
            className="flex h-10 w-10 shrink-0 items-center justify-center text-foreground/80 transition-colors hover:text-destructive disabled:opacity-40"
            onClick={() => onChange(values.filter((_, itemIndex) => itemIndex !== index))}
          >
            <IconTrash size={18} />
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={disabled || values.length >= 20}
        className="flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent disabled:opacity-40"
        onClick={() => onChange([...values, ''])}
      >
        <IconPlus size={16} />
        {isZh ? '添加来源' : 'Add origin'}
      </button>
    </div>
  )
}
