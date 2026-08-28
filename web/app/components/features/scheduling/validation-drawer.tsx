'use client'

import { IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { RuleViolation } from '@/models/scheduling-rule'
import { violationText, violationSubject } from './violation-utils'

export type ValidationDrawerProps = {
  open: boolean
  items: RuleViolation[]
  hardCount: number
  softCount: number
  onClose: () => void
}

/** Right-side drawer listing draft-schedule violations (hard first). */
export function ValidationDrawer({ open, items, hardCount, softCount, onClose }: ValidationDrawerProps) {
  const { locale } = useLocaleStore()
  if (!open) return null

  const hard = items.filter((v) => v.level === 'hard')
  const soft = items.filter((v) => v.level !== 'hard')

  const renderGroup = (title: string, list: RuleViolation[], level: 'hard' | 'soft') => (
    <div>
      <div className="px-4 pb-1.5 pt-3 text-xs font-semibold text-muted-foreground">
        {title}（{list.length}）
      </div>
      <ul className="space-y-1.5 px-3 pb-3">
        {list.map((v, i) => (
          <li
            key={i}
            className={`rounded-lg border px-3 py-2 text-xs ${
              level === 'hard'
                ? 'border-red-200 bg-red-50/60'
                : 'border-amber-200 bg-amber-50/60'
            }`}
          >
            <div className="flex items-center gap-1.5 font-medium">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  level === 'hard' ? 'bg-red-500' : 'bg-amber-500'
                }`}
              />
              <span className="truncate">{violationSubject(v)}</span>
              <span className="shrink-0 text-muted-foreground tabular-nums">{v.date}</span>
            </div>
            <div className="mt-1 pl-3 text-muted-foreground">{violationText(v, locale)}</div>
          </li>
        ))}
      </ul>
    </div>
  )

  return (
    <div className="absolute inset-y-0 right-0 z-30 flex w-80 flex-col border-l border-border bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="text-sm font-semibold">
          {t('scheduling.violations.drawer.title', locale)}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {t('scheduling.violations.drawer.counts', locale, { hard: hardCount, soft: softCount })}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-muted"
          aria-label={t('scheduling.violations.drawer.close', locale)}
        >
          <IconX size={15} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto pb-4">
        {items.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-muted-foreground">
            {t('scheduling.violations.drawer.empty', locale)}
          </p>
        ) : (
          <>
            {hard.length > 0 && renderGroup(t('scheduling.violations.drawer.hard', locale), hard, 'hard')}
            {soft.length > 0 && renderGroup(t('scheduling.violations.drawer.soft', locale), soft, 'soft')}
          </>
        )}
      </div>
    </div>
  )
}
