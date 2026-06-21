'use client'

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Popover } from '@base-ui/react/popover'
import { IconChevronDown } from '@tabler/icons-react'
import { toast } from 'sonner'
import { HTTPError } from 'ky'
import { useLocaleStore } from '@/context/locale-store'
import { useUpdateAgentMaxConcurrent } from '@/service/use-conversations'
import { t } from '@/utils/i18n'
import type { AgentStats } from '@/models/conversation'

type Props = {
  agentStats: AgentStats
  open: boolean
  onOpenChange: (open: boolean) => void
}

function parseMaxConcurrentInput(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  if (!Number.isInteger(parsed) || parsed < 1) return null
  return parsed
}

export function MaxConcurrentPopover({ agentStats, open, onOpenChange }: Props) {
  const { locale } = useLocaleStore()
  const inputRef = useRef<HTMLInputElement>(null)
  const updateMaxConcurrent = useUpdateAgentMaxConcurrent()
  const [draftValue, setDraftValue] = useState(String(agentStats.max_concurrent))
  const [validationError, setValidationError] = useState<string | null>(null)

  const parsedValue = parseMaxConcurrentInput(draftValue)
  const showCapacityWarning =
    parsedValue !== null && parsedValue < agentStats.current_count
  const hasChanges = parsedValue !== null && parsedValue !== agentStats.max_concurrent
  const canSave = hasChanges && parsedValue !== null && !updateMaxConcurrent.isPending

  useEffect(() => {
    if (!open) return
    setDraftValue(String(agentStats.max_concurrent))
    setValidationError(null)
    const timer = window.setTimeout(() => {
      inputRef.current?.focus()
      inputRef.current?.select()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [open, agentStats.max_concurrent])

  const closePopover = () => {
    onOpenChange(false)
    setValidationError(null)
  }

  const handleSave = async () => {
    const nextValue = parseMaxConcurrentInput(draftValue)
    if (nextValue === null) {
      setValidationError(t('ws.chat.maxConcurrent.validation', locale))
      return
    }
    if (nextValue === agentStats.max_concurrent) {
      return
    }

    setValidationError(null)
    try {
      await updateMaxConcurrent.mutateAsync(nextValue)
      toast.success(t('ws.chat.maxConcurrent.saveSuccess', locale))
      closePopover()
    } catch (error) {
      if (error instanceof HTTPError && error.response.status === 403) {
        toast.error(t('ws.chat.maxConcurrent.noPermission', locale))
      } else {
        toast.error(t('ws.chat.maxConcurrent.saveFailed', locale))
      }
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (canSave) {
      void handleSave()
    }
  }

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      if (canSave) {
        void handleSave()
      }
    }
  }

  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger
        type="button"
        aria-label={t('ws.chat.maxConcurrent.editAria', locale)}
        className="inline-flex items-center gap-1 font-semibold text-[#1a1a1a] transition-colors hover:text-[#333333]"
      >
        <span>
          {agentStats.current_count} / {agentStats.max_concurrent}
        </span>
        <IconChevronDown size={14} className="text-[#999999]" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="end">
          <Popover.Popup className="z-50 w-[240px] rounded-lg border border-[#E5E5E5] bg-white p-4 shadow-lg">
            <form onSubmit={handleSubmit} className="space-y-3">
              <h3 className="text-sm font-medium text-[#1a1a1a]">
                {t('ws.chat.maxConcurrent.title', locale)}
              </h3>
              <div className="space-y-1.5">
                <input
                  ref={inputRef}
                  id="max-concurrent-input"
                  type="number"
                  min={1}
                  step={1}
                  inputMode="numeric"
                  aria-label={t('ws.chat.maxConcurrent.title', locale)}
                  value={draftValue}
                  disabled={updateMaxConcurrent.isPending}
                  onChange={(event) => {
                    setDraftValue(event.target.value)
                    if (validationError) setValidationError(null)
                  }}
                  onKeyDown={handleInputKeyDown}
                  className="h-9 w-[120px] rounded-md border border-[#E5E5E5] px-3 text-sm outline-none focus:border-[#999999]"
                />
                <p className="text-xs text-muted-foreground">
                  {t('ws.chat.maxConcurrent.description', locale)}
                </p>
                {validationError && (
                  <p className="text-xs text-destructive">{validationError}</p>
                )}
              </div>
              <p className="text-xs text-[#737373]">
                {t('ws.chat.maxConcurrent.currentCount', locale, {
                  count: agentStats.current_count,
                })}
              </p>
              {showCapacityWarning && (
                <p className="rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
                  {t('ws.chat.maxConcurrent.capacityWarning', locale)}
                </p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  disabled={updateMaxConcurrent.isPending}
                  onClick={closePopover}
                  className="rounded-md px-3 py-1.5 text-xs font-medium text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-50"
                >
                  {t('ws.chat.maxConcurrent.cancel', locale)}
                </button>
                <button
                  type="submit"
                  disabled={!canSave}
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {updateMaxConcurrent.isPending
                    ? t('ws.chat.maxConcurrent.saving', locale)
                    : t('ws.chat.maxConcurrent.save', locale)}
                </button>
              </div>
            </form>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function ReceptionStatsCapsule({
  agentStats,
  editable,
  maxConcurrentOpen,
  onMaxConcurrentOpenChange,
}: {
  agentStats: AgentStats
  editable: boolean
  maxConcurrentOpen: boolean
  onMaxConcurrentOpenChange: (open: boolean) => void
}) {
  const { locale } = useLocaleStore()

  if (editable) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-[14px] bg-[#EBEBEB] px-3 py-1 text-[12px] transition-colors hover:bg-[#E0E0E0]">
        <span className="font-medium text-[#737373]">{t('ws.chat.receptionLabel', locale)}</span>
        <MaxConcurrentPopover
          agentStats={agentStats}
          open={maxConcurrentOpen}
          onOpenChange={onMaxConcurrentOpenChange}
        />
      </span>
    )
  }

  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-[14px] bg-[#EBEBEB] px-3 py-1 text-[12px]">
      <span className="font-medium text-[#737373]">{t('ws.chat.receptionLabel', locale)}</span>
      <span className="font-semibold text-[#1a1a1a]">
        {agentStats.current_count} / {agentStats.max_concurrent}
      </span>
    </span>
  )
}
