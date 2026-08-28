'use client'

import { IconMicrophone, IconUser } from '@tabler/icons-react'

import { PersonalAutoOutboundBusinessPanel } from '@/app/components/features/call-center/personal-auto-outbound-business-panel'
import { useLocaleStore } from '@/context/locale-store'
import type { IncomingCall } from '@/lib/call-session-reducer'
import { maskPhone } from '@/app/components/features/call-center/personal-auto-outbound-lanes'
import { usePersonalAutoOutboundBusinessContext } from '@/service/use-personal-auto-outbound'
import { t } from '@/utils/i18n'

export function PersonalAutoOutboundTaskPop({
  incoming,
  phase,
  onSubmitted,
}: {
  incoming: IncomingCall | null
  phase: string
  onSubmitted: () => void
}) {
  const { locale } = useLocaleStore()
  const callId = Number(incoming?.record_id || 0)
  const contextQuery = usePersonalAutoOutboundBusinessContext(callId, callId > 0)
  const context = contextQuery.data
  const name = context?.target_name || (context?.target_phone ? maskPhone(context.target_phone) : incoming?.from || '')
  const phone = context?.target_phone ? maskPhone(context.target_phone) : incoming?.from || ''
  const statusLabel = phase === 'wrap_up' ? t('personalAuto.taskPop.wrapUp', locale) : t('personalAuto.taskPop.onCall', locale)
  const openingScript = context?.opening_script_text?.trim() || ''
  const lastUtterance = context?.last_utterance?.trim() || ''
  const contextFailed = contextQuery.isError

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        {contextQuery.isLoading ? (
          <div className="h-20 animate-pulse rounded-lg bg-muted/40" />
        ) : (
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{name || t('personalAuto.taskPop.unknown', locale)}</h2>
              <span className="rounded-md bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">{statusLabel}</span>
            </div>
            <p className="mt-1 font-mono text-xl font-semibold tracking-wide">{phone}</p>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
              <IconUser size={13} />
              {t('personalAuto.taskPop.sourceTask', locale, { task: context?.task_name ?? '—' })}
            </p>
            {incoming?.personal_assignment_type === 'fallback' && (
              <p className="mt-2 text-[11px] text-warning-foreground">{t('personalAuto.fallbackHandoffHint', locale)}</p>
            )}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">{t('personalAuto.taskPop.contextTitle', locale)}</h3>
        <p className="mt-1 text-[11px] text-muted-foreground">{t('personalAuto.taskPop.contextHint', locale)}</p>
        {contextQuery.isLoading ? (
          <div className="mt-4 h-16 animate-pulse rounded-lg bg-muted/40" />
        ) : contextFailed ? (
          <p className="mt-4 text-sm text-muted-foreground">{t('personalAuto.taskPop.contextFailed', locale)}</p>
        ) : (
          <div className="mt-4 space-y-3">
            {openingScript ? (
              <div className="rounded-lg bg-muted/60 px-4 py-3">
                <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                  <IconMicrophone size={13} />
                  {t('personalAuto.taskPop.opening', locale)}
                </div>
                <p className="mt-1.5 text-sm leading-6">{openingScript}</p>
              </div>
            ) : null}
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
              <div className="text-[11px] font-medium text-primary">
                {lastUtterance ? t('personalAuto.taskPop.lastSaid', locale) : t('personalAuto.taskPop.silent', locale)}
              </div>
              {lastUtterance ? <p className="mt-1.5 text-sm font-medium leading-6">{lastUtterance}</p> : null}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-border bg-card shadow-sm">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold">{t('personalAuto.taskPop.fields', locale)}</h3>
        </div>
        <div className="p-5">
          <PersonalAutoOutboundBusinessPanel
            incoming={incoming}
            onSubmitted={onSubmitted}
          />
        </div>
      </section>
    </div>
  )
}
