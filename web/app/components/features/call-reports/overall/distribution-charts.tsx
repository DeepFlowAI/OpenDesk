'use client'

import { useMemo } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import type { CallMetricDistribution } from '@/models/call-report-overall'
import { t } from '@/utils/i18n'
import { CallDistributionPie } from './distribution-pie'
import { CallFunnelCard } from './funnel-card'
import {
  callDistributionLabel,
  callDistributionSliceLabel,
} from './metric-format'

export function CallDistributionCharts({
  distributions,
  loading,
}: {
  distributions: CallMetricDistribution[]
  loading?: boolean
}) {
  if (distributions.length === 0) return null
  return (
    <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {distributions.map((distribution) => (
        <DistributionCard
          key={distribution.key}
          distribution={distribution}
          loading={loading}
        />
      ))}
    </div>
  )
}

function DistributionCard({
  distribution,
  loading,
}: {
  distribution: CallMetricDistribution
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  const title = callDistributionLabel(distribution.key, locale)
  const slices = useMemo(
    () => distribution.slices.map((slice) => ({
      ...slice,
      displayLabel: callDistributionSliceLabel(distribution.key, slice, locale),
    })),
    [distribution, locale],
  )
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)

  return (
    <section className="min-h-[220px] rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-medium text-foreground">{title}</h4>
        <span className="shrink-0 text-xs text-muted-foreground">
          {t('ws.records.callReports.overall.distribution.total', locale, {
            count: total.toLocaleString(locale),
          })}
        </span>
      </div>
      {loading ? (
        <div className="mt-3 h-[160px] animate-pulse rounded-md bg-muted" aria-busy="true" />
      ) : total === 0 ? (
        <div className="mt-3 flex h-[160px] items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
          {t('ws.records.callReports.overall.distribution.noData', locale)}
        </div>
      ) : distribution.key === 'inbound_human_funnel' ? (
        <CallFunnelCard distribution={distribution} />
      ) : (
        <>
          <CallDistributionPie
            label={title}
            locale={locale}
            otherLabel={t('ws.records.callReports.overall.enum.other', locale)}
            slices={slices}
          />
          {slices.length > 8 ? (
            <details className="mt-2 text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none text-foreground">
                {t('ws.records.callReports.overall.distribution.showAll', locale)}
              </summary>
              <div className="mt-2 max-h-40 space-y-1 overflow-auto pr-2">
                {slices.map((slice) => (
                  <div key={slice.key} className="flex justify-between gap-3">
                    <span>{slice.displayLabel}</span>
                    <span className="font-mono text-foreground">
                      {slice.value.toLocaleString(locale)} ({((slice.value / total) * 100).toFixed(1)}%)
                    </span>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </>
      )}
    </section>
  )
}
