'use client'
import { useState } from 'react'
import { Popover } from '@base-ui/react/popover'
import { IconNotebook, IconX } from '@tabler/icons-react'

export function FlowInfoPopover({
  name,
  description,
  onChange,
}: {
  name: string
  description: string
  onChange: (next: { name: string; description: string }) => void
}) {
  const [open, setOpen] = useState(false)
  const [localName, setLocalName] = useState(name)
  const [localDesc, setLocalDesc] = useState(description)

  const onOpen = (next: boolean) => {
    if (next) {
      setLocalName(name)
      setLocalDesc(description)
    }
    setOpen(next)
  }

  return (
    <Popover.Root open={open} onOpenChange={onOpen}>
      <Popover.Trigger
        className="rounded p-1 text-muted-foreground hover:bg-muted"
        aria-label="流程信息"
      >
        <IconNotebook size={18} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={8} align="start">
          <Popover.Popup className="z-50 w-[360px] rounded-xl border border-border bg-white p-5 shadow-lg">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold">流程信息</h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-foreground/60 hover:text-foreground"
              >
                <IconX size={16} />
              </button>
            </div>
            <div className="mt-3 space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-foreground/80">流程名称</label>
                <input
                  type="text"
                  value={localName}
                  onChange={(e) => setLocalName(e.target.value)}
                  maxLength={50}
                  className="h-9 w-full rounded-md border border-border px-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-foreground/80">流程描述</label>
                <textarea
                  value={localDesc}
                  onChange={(e) => setLocalDesc(e.target.value)}
                  rows={4}
                  maxLength={200}
                  className="w-full rounded-md border border-border px-2 py-1.5 text-sm"
                />
                <p className="mt-1 text-xs text-foreground/60">支持最多 200 字</p>
              </div>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="h-9 rounded-md border border-border px-3 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  onChange({ name: localName.trim() || name, description: localDesc.trim() })
                  setOpen(false)
                }}
                className="h-9 rounded-md bg-black px-4 text-sm font-medium text-white"
              >
                保存
              </button>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
