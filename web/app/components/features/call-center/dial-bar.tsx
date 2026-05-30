'use client'

import { useState } from 'react'
import { IconDialpad, IconPhone } from '@tabler/icons-react'
import { toast } from 'sonner'

import { DialPad } from '@/app/components/features/call-center/dial-pad'
import { OutboundNumberSelect } from '@/app/components/features/call-center/outbound-number-select'
import { dialOutbound } from '@/service/use-call-center'

const DIAL_INPUT_PATTERN = /^[\d+\-*#\s]*$/

type DialBarProps = {
  disabled?: boolean
  statusHint?: string
  onDialNumberChange?: (number: string) => void
  onOutboundNumberChange?: (id: string, phoneNumber: string) => void
  onDialStarted?: (info: { callId: string; destination: string; outboundNumber: string }) => void
}

export function DialBar({
  disabled,
  statusHint,
  onDialNumberChange,
  onOutboundNumberChange,
  onDialStarted,
}: DialBarProps) {
  const [dialNumber, setDialNumber] = useState('')
  const [outboundId, setOutboundId] = useState('')
  const [outboundNumber, setOutboundNumber] = useState('')
  const [keypadOpen, setKeypadOpen] = useState(false)
  const [dialing, setDialing] = useState(false)
  const trimmedDialNumber = dialNumber.trim()
  const canDial = !disabled && !dialing && trimmedDialNumber.length > 0 && !!outboundId

  const updateDialNumber = (next: string) => {
    if (!DIAL_INPUT_PATTERN.test(next)) return
    setDialNumber(next)
    onDialNumberChange?.(next)
  }

  const appendDigit = (key: string) => {
    updateDialNumber(dialNumber + key)
  }

  const handleBackspace = () => {
    updateDialNumber(dialNumber.slice(0, -1))
  }

  const handleOutboundChange = (id: string, phoneNumber: string) => {
    setOutboundId(id)
    setOutboundNumber(phoneNumber)
    onOutboundNumberChange?.(id, phoneNumber)
  }

  const handleDialClick = async () => {
    if (!canDial) return
    setDialing(true)
    try {
      const resp = await dialOutbound({
        outbound_phone_number_id: outboundId,
        destination: trimmedDialNumber,
      })
      onDialStarted?.({
        callId: resp.call_id,
        destination: trimmedDialNumber,
        outboundNumber,
      })
    } catch (err) {
      // Backend ValidationError → 422 with a JSON body carrying detail
      const message = err instanceof Error ? err.message : '外呼失败'
      toast.error(message)
    } finally {
      setDialing(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <div className="relative">
        <input
          type="text"
          inputMode="tel"
          value={dialNumber}
          onChange={(e) => updateDialNumber(e.target.value)}
          placeholder="输入用户号码"
          disabled={disabled}
          className="h-10 w-[220px] rounded-lg border border-border py-2 pl-3 pr-9 text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60"
        />
        <div className="absolute inset-y-0 right-1 flex items-center">
          <DialPad
            open={keypadOpen}
            onOpenChange={setKeypadOpen}
            onKeyPress={appendDigit}
            onBackspace={handleBackspace}
            disabled={disabled}
            trigger={<IconDialpad size={18} />}
          />
        </div>
      </div>

      <OutboundNumberSelect
        value={outboundId}
        onChange={handleOutboundChange}
        disabled={disabled}
      />

      <button
        type="button"
        onClick={handleDialClick}
        disabled={!canDial}
        title={
          dialing
            ? '正在拨号...'
            : canDial
              ? '发起外呼'
              : '请输入号码并选择外呼号码'
        }
        className="rounded-full bg-green-500 p-2.5 text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        <IconPhone size={18} />
      </button>

      {statusHint && (
        <span className="ml-auto text-xs text-muted-foreground">{statusHint}</span>
      )}
    </div>
  )
}
