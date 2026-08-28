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
  /** Overrides the trigger button chrome (e.g. the console's icon-op styling). */
  triggerClassName?: string
  /** Overrides the trigger's aria-label (defaults to "数字键盘"). */
  triggerAriaLabel?: string
  onKeyPress: (key: string) => void
  /** Optional because `backspaceDisabled` hides the key during a live call. */
  onBackspace?: () => void
  disabled?: boolean
  /** Greys out the keys and explains why, e.g. DTMF blocked while on hold. */
  keysDisabledReason?: string
  /** Hides backspace: during a call a sent key cannot be taken back. */
  backspaceDisabled?: boolean
}

export function DialPad({
  open,
  onOpenChange,
  trigger,
  triggerClassName,
  triggerAriaLabel,
  onKeyPress,
  onBackspace,
  disabled,
  keysDisabledReason,
  backspaceDisabled,
}: DialPadProps) {
  const keysDisabled = Boolean(keysDisabledReason)
  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger
        type="button"
        disabled={disabled}
        className={
          triggerClassName ??
          'inline-flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40'
        }
        aria-label={triggerAriaLabel ?? '数字键盘'}
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
                  disabled={keysDisabled}
                  title={keysDisabledReason}
                  className="grid h-11 w-11 place-items-center rounded-lg border border-border bg-white text-base font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white"
                >
                  {key}
                </button>
              ))}
              {!backspaceDisabled && (
                <button
                  type="button"
                  onClick={onBackspace}
                  className="col-span-3 flex h-9 items-center justify-center gap-1 rounded-lg border border-border bg-white text-sm text-muted-foreground hover:bg-muted"
                >
                  <IconBackspace size={16} />
                  删除
                </button>
              )}
            </div>
            {keysDisabledReason && (
              <p className="mt-2 max-w-[168px] text-xs text-muted-foreground">
                {keysDisabledReason}
              </p>
            )}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
