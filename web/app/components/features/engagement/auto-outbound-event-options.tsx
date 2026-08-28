'use client'

import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type EventDefinition = { code: string; labelKey: string; descriptionKey: string }
type EventGroupDefinition = { key: string; titleKey: string; events: EventDefinition[] }

export const AUTO_OUTBOUND_EVENT_GROUPS: EventGroupDefinition[] = [
  {
    key: 'task',
    titleKey: 'ws.autoOutbound.subscription.group.task',
    events: [
      ['updated', 'auto_outbound.task.updated'], ['started', 'auto_outbound.task.started'],
      ['paused', 'auto_outbound.task.paused'], ['resumed', 'auto_outbound.task.resumed'],
      ['completed', 'auto_outbound.task.completed'], ['archived', 'auto_outbound.task.archived'],
      ['deleted', 'auto_outbound.task.deleted'],
    ].map(([key, code]) => ({
      code,
      labelKey: `ws.autoOutbound.subscription.event.${key}`,
      descriptionKey: `ws.autoOutbound.subscription.event.${key}.desc`,
    })),
  },
  {
    key: 'call',
    titleKey: 'ws.autoOutbound.subscription.group.call',
    events: [
      ['callStarted', 'auto_outbound.call.started'],
      ['callAnswered', 'auto_outbound.call.answered'],
      ['callEnded', 'auto_outbound.call.ended'],
    ].map(([key, code]) => ({
      code,
      labelKey: `ws.autoOutbound.subscription.event.${key}`,
      descriptionKey: `ws.autoOutbound.subscription.event.${key}.desc`,
    })),
  },
  {
    key: 'business',
    titleKey: 'ws.autoOutbound.subscription.group.business',
    events: [
      ['businessSubmitted', 'auto_outbound.business_record.submitted'],
      ['businessUpdated', 'auto_outbound.business_record.updated'],
    ].map(([key, code]) => ({
      code,
      labelKey: `ws.autoOutbound.subscription.event.${key}`,
      descriptionKey: `ws.autoOutbound.subscription.event.${key}.desc`,
    })),
  },
]

export function AutoOutboundEventOptions({
  locale,
  selected,
  onChange,
  error,
}: {
  locale: Locale
  selected: string[]
  onChange: (value: string[]) => void
  error?: string
}) {
  const selectedSet = new Set(selected)
  const toggle = (code: string, checked: boolean) => {
    onChange(checked ? [...selected, code] : selected.filter((item) => item !== code))
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t('ws.autoOutbound.subscription.events', locale)}</span>
        <span className="text-xs text-muted-foreground">
          {t('ws.autoOutbound.subscription.selectedCount', locale, { count: selected.length })}
        </span>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {AUTO_OUTBOUND_EVENT_GROUPS.map((group) => (
        <section key={group.key} className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-medium">{t(group.titleKey, locale)}</h3>
            <Button
              type="button"
              variant="link"
              size="xs"
              onClick={() => onChange(Array.from(new Set([...selected, ...group.events.map((item) => item.code)])))}
            >
              {t('ws.autoOutbound.subscription.selectGroup', locale)}
            </Button>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {group.events.map((event) => (
              <label key={event.code} className="flex cursor-pointer items-start gap-2">
                <Checkbox
                  checked={selectedSet.has(event.code)}
                  onCheckedChange={(checked) => toggle(event.code, checked === true)}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{t(event.labelKey, locale)}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {t(event.descriptionKey, locale)}
                  </span>
                  <span className="mt-1 block break-all font-mono text-[10px] text-muted-foreground">
                    {event.code}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
