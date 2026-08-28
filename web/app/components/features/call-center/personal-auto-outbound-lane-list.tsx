'use client'

import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

import type { LaneSlot } from './personal-auto-outbound-lanes'

function laneMeta(slot: LaneSlot, locale: Locale) {
  if (slot.stage === 'dialing') return { label: t('personalAuto.stage.dialing', locale), bar: 'bg-info', text: 'text-info' }
  if (slot.stage === 'ringing') return { label: t('personalAuto.stage.ringing', locale), bar: 'bg-info', text: 'text-info' }
  if (slot.stage === 'screening') return { label: t('personalAuto.stage.screening', locale), bar: 'bg-warning', text: 'text-foreground' }
  return { label: t('personalAuto.lane.idle', locale), bar: 'bg-transparent', text: 'text-muted-foreground' }
}

function clearingResultLabel(result: string | undefined, locale: Locale) {
  if (!result) return t('personalAuto.stage.ended', locale)
  const resultText = t(`personalAuto.result.${result}`, locale)
  if (resultText !== `personalAuto.result.${result}`) return resultText
  const stageText = t(`personalAuto.stage.${result}`, locale)
  if (stageText !== `personalAuto.stage.${result}`) return stageText
  return result
}

export function PersonalAutoOutboundLanes({
  lanes,
  locale,
}: {
  lanes: LaneSlot[]
  locale: Locale
}) {
  return (
    <section className="flex flex-col gap-3">
      {lanes.map((lane) => {
        const empty = lane.stage === 'empty'
        const clearing = lane.stage === 'clearing'
        const meta = lane.stage === 'clearing'
          ? {
              label: t('personalAuto.lane.clearing', locale, { result: clearingResultLabel(lane.result, locale) }),
              bar: 'bg-muted-foreground/30',
              text: 'text-muted-foreground',
            }
          : laneMeta(lane, locale)
        return (
          <div
            key={lane.slot}
            role="group"
            aria-label={t('personalAuto.lane.aria', locale, {
              slot: lane.slot,
              customer: lane.customer ?? t('personalAuto.lane.idle', locale),
              stage: meta.label,
              elapsed: lane.elapsed ?? '',
            })}
            className={`rounded-xl border px-5 py-4 ${
              clearing
                ? 'border-border/60 bg-card/50 opacity-45'
                : empty
                  ? 'border-dashed border-border bg-muted/20'
                  : lane.stage === 'screening'
                    ? 'border-warning/40 bg-warning/5'
                    : 'border-border bg-card'
            }`}
          >
            <div className="flex items-center gap-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-muted font-mono text-[11px] font-semibold text-muted-foreground">
                {lane.slot}
              </span>
              {empty ? (
                <div className="min-w-0 flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-0" />
                  </div>
                </div>
              ) : (
                <>
                  <div className="w-[168px] shrink-0">
                    <div className="truncate text-sm font-semibold">{lane.customer}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{lane.phone}</div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className={`h-full rounded-full ${meta.bar}`}
                        style={{ width: `${clearing ? 0 : lane.progress ?? 0}%` }}
                      />
                    </div>
                  </div>
                </>
              )}
              <div className={`w-[148px] shrink-0 text-right text-xs font-medium ${meta.text}`}>
                {empty ? t('personalAuto.lane.idle', locale) : meta.label}
              </div>
              <div className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
                {empty || clearing ? '' : lane.elapsed}
              </div>
            </div>
          </div>
        )
      })}
    </section>
  )
}
