'use client'

import { useMemo, useState } from 'react'
import {
  IconAlertTriangle,
  IconCheck,
  IconChevronDown,
  IconDeviceLandlinePhone,
  IconWorld,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { useCallCenterRuntime } from '@/context/call-center-runtime'
import {
  useMyCallDevices,
  useMyCurrentCallDevice,
  useSetMyCurrentCallDevice,
} from '@/service/use-agent-devices'
import type { AgentCallDevice, CallDeviceType } from '@/models/call-device'
import type { Locale } from '@/lib/languages'

/**
 * Call-device selector for the call-center workspace. Renders the devices the
 * backend reports for the current agent (Web phone, SIP phone, and any future
 * types) using generic "call device" semantics — it never hard-codes
 * "not-browser means SIP". Switching is only allowed while the agent is idle.
 */
export function CallDeviceSelector() {
  const { locale } = useLocaleStore()
  const { phase, mic } = useCallCenterRuntime()
  const [open, setOpen] = useState(false)

  const { data: devicesData, isLoading: devicesLoading } = useMyCallDevices({ refetchInterval: 15_000 })
  const { data: current, isLoading: currentLoading } = useMyCurrentCallDevice()
  const setDevice = useSetMyCurrentCallDevice()

  const devices = devicesData?.items ?? []
  const currentType = current?.device_type ?? null

  // Only idle agents may switch devices; ringing / dialing / on-call lock it.
  const switchingLocked = phase !== 'idle' && phase !== 'wrap_up'
  const inCall = phase === 'incoming' || phase === 'outbound_ringing' || phase === 'on_call'

  const currentDevice = useMemo(
    () => devices.find((device) => device.device_type === currentType) ?? null,
    [devices, currentType],
  )

  const handleSelect = async (device: AgentCallDevice) => {
    setOpen(false)
    if (device.device_type === currentType) return
    if (!device.available) return
    const previousLabel = currentDevice?.name
    try {
      await setDevice.mutateAsync(device.device_type)
      toast.success(t('se.device.switched', locale, { name: deviceLabel(device, locale) }))
    } catch {
      // The mutation invalidates and refetches, restoring the real current
      // device. Surface a readable reason.
      toast.error(
        previousLabel
          ? t('se.device.switchFailedRestore', locale, { name: previousLabel })
          : t('se.device.switchFailed', locale),
      )
    }
  }

  const loading = devicesLoading || currentLoading
  const currentLabel = currentDevice ? deviceLabel(currentDevice, locale) : t('se.device.none', locale)
  const currentUnavailable = currentDevice != null && !currentDevice.available

  return (
    <div className="mt-4">
      <h3 className="mb-2 text-[11px] font-semibold text-foreground/70">{t('se.device.label', locale)}</h3>

      <div className="relative">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          disabled={loading || switchingLocked || setDevice.isPending}
          onClick={() => setOpen((prev) => !prev)}
          title={switchingLocked ? t('se.device.lockedTooltip', locale) : undefined}
          className={cn(
            'flex h-10 w-full items-center gap-2 rounded-md border border-border px-3 text-left text-[13px] transition-colors',
            loading || switchingLocked || setDevice.isPending
              ? 'cursor-not-allowed bg-muted/50 opacity-70'
              : 'bg-white hover:bg-muted/50',
          )}
        >
          <DeviceIcon type={currentDevice?.device_type ?? null} />
          <span className="min-w-0 flex-1 truncate font-medium text-foreground">{currentLabel}</span>
          {currentDevice?.device_type === 'sip_phone' && (
            <HeartbeatDot device={currentDevice} locale={locale} />
          )}
          {setDevice.isPending ? (
            <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
          ) : (
            <IconChevronDown size={16} className="shrink-0 text-[#999999]" />
          )}
        </button>

        {open && !switchingLocked && !loading && (
          <div
            role="menu"
            className="absolute left-0 top-full z-50 mt-1 w-full overflow-hidden rounded-lg border border-border bg-white py-1 shadow-lg"
          >
            {devices.map((device) => {
              const active = device.device_type === currentType
              const disabled = !device.available && !active
              return (
                <button
                  key={device.device_type}
                  type="button"
                  role="menuitem"
                  disabled={disabled}
                  onClick={() => handleSelect(device)}
                  className={cn(
                    'flex w-full items-start gap-2 px-3 py-2 text-left text-[13px] transition-colors',
                    disabled
                      ? 'cursor-not-allowed opacity-60'
                      : 'text-[#1a1a1a] hover:bg-[#F5F5F5]',
                  )}
                >
                  <span className="mt-0.5">
                    <DeviceIcon type={device.device_type} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate font-medium">{deviceLabel(device, locale)}</span>
                      {device.device_type === 'sip_phone' && <HeartbeatDot device={device} locale={locale} />}
                    </span>
                    {device.available && device.status_message && (
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {device.status_message}
                      </span>
                    )}
                    {!device.available && device.unavailable_reason && (
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {device.unavailable_reason}
                      </span>
                    )}
                    {device.device_type === 'webrtc' && !device.available && mic.state === 'denied' && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          void mic.request()
                        }}
                        className="mt-1 text-xs font-medium text-primary hover:underline"
                      >
                        {t('se.device.grantMic', locale)}
                      </button>
                    )}
                  </span>
                  {active && <IconCheck size={14} className="mt-0.5 shrink-0 text-[#22C55E]" />}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {currentDevice == null && !loading && (
        <p className="mt-2 text-xs text-muted-foreground">{t('se.device.selectPrompt', locale)}</p>
      )}

      {current?.unavailable_reason && !currentType && !loading && (
        <div
          role="alert"
          className="mt-2 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-800"
        >
          <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{current.unavailable_reason}</span>
        </div>
      )}

      {currentDevice?.device_type === 'sip_phone' && currentUnavailable && !inCall && (
        <div
          role="alert"
          className="mt-2 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-[11px] text-red-700"
        >
          <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            {currentDevice.unavailable_reason || t('se.device.sipBanner', locale)}
          </span>
        </div>
      )}
    </div>
  )
}

function deviceLabel(device: AgentCallDevice, locale: Locale): string {
  if (device.device_type === 'sip_phone' && device.extension_number) {
    return `${device.name} · ${device.extension_number}`
  }
  return device.name
}

function DeviceIcon({ type }: { type: CallDeviceType | null }) {
  if (type === 'sip_phone') {
    return <IconDeviceLandlinePhone size={16} className="shrink-0 text-muted-foreground" />
  }
  return <IconWorld size={16} className="shrink-0 text-muted-foreground" />
}

/**
 * Always-on small heartbeat dot for the SIP phone. Colour alone is never the
 * only signal — the accessible name and title carry the connection text and
 * last-updated time as well.
 */
function HeartbeatDot({ device, locale }: { device: AgentCallDevice; locale: Locale }) {
  const connected = device.registration_status === 'registered' && device.available
  const statusText = connected ? t('se.device.connected', locale) : t('se.device.disconnected', locale)
  const reason = !connected && device.unavailable_reason ? ` · ${device.unavailable_reason}` : ''
  const label = `${statusText}${reason}`
  return (
    <span
      role="status"
      tabIndex={0}
      aria-label={label}
      title={label}
      className={cn(
        'inline-block h-2 w-2 shrink-0 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring',
        connected ? 'bg-[#22C55E]' : 'bg-red-500',
      )}
    />
  )
}
