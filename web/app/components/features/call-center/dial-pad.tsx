'use client'

import { Popover } from '@base-ui/react/popover'
import { IconBackspace } from '@tabler/icons-react'

const KEY_ROWS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['*', '0', '#'],
] as const

type DialPadProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  trigger: React.ReactNode
  onKeyPress: (key: string) => void
  onBackspace: () => void
  disabled?: boolean
}

export function DialPad({
  open,
  onOpenChange,
  trigger,
  onKeyPress,
  onBackspace,
  disabled,
}: DialPadProps) {
  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger
        type="button"
        disabled={disabled}
        className="inline-flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="数字键盘"
      >
        {trigger}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="end">
          <Popover.Popup className="z-50 rounded-xl border border-border bg-white p-3 shadow-lg">
            <div className="grid grid-cols-3 gap-2">
              {KEY_ROWS.flat().map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => onKeyPress(key)}
                  className="grid h-11 w-11 place-items-center rounded-lg border border-border bg-white text-base font-medium hover:bg-muted"
                >
                  {key}
                </button>
              ))}
              <button
                type="button"
                onClick={onBackspace}
                className="col-span-3 flex h-9 items-center justify-center gap-1 rounded-lg border border-border bg-white text-sm text-muted-foreground hover:bg-muted"
              >
                <IconBackspace size={16} />
                删除
              </button>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
