'use client'

import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts/core'
import { PieChart as EChartsPieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { MetricDistribution, MetricDistributionSlice } from '@/models/session-report-overall'
import { distributionLabelKey, distributionSliceDisplayLabel } from './metric-format'

echarts.use([
  EChartsPieChart,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

const CHART_COLOR_TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'] as const
const CHART_COLOR_FALLBACKS = ['#6b78d6', '#3ea6ad', '#54ad7e', '#d6a23e', '#d97089']

type LocalizedSlice = MetricDistributionSlice & {
  displayLabel: string
}

type PieTooltipParam = {
  marker?: string
  name?: string
  value?: number | string
}

type Props = {
  distributions: MetricDistribution[]
  loading?: boolean
}

export function SatisfactionDistributionCharts({ distributions, loading }: Props) {
  if (distributions.length === 0) return null

  return (
    <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
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
  distribution: MetricDistribution
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  const slices = useMemo(
    () =>
      distribution.slices.map((slice) => ({
        ...slice,
        displayLabel: distributionSliceDisplayLabel(distribution.key, slice, locale),
      })),
    [distribution.key, distribution.slices, locale],
  )
  const hasData = distribution.total > 0 && slices.some((slice) => slice.value > 0)

  return (
    <div className="min-h-[232px] rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-xs font-medium text-muted-foreground">
          {t(distributionLabelKey(distribution.key), locale)}
        </h4>
        <span className="shrink-0 text-xs text-muted-foreground">
          {t('ws.records.sessionReports.overall.distribution.total', locale, {
            count: distribution.total.toLocaleString(),
          })}
        </span>
      </div>
      {loading ? (
        <div className="mt-3 h-[172px] animate-pulse rounded-md bg-muted" aria-busy="true" />
      ) : hasData ? (
        <DistributionPie slices={slices} />
      ) : (
        <div className="mt-3 flex h-[172px] items-center justify-center rounded-md border border-dashed border-border text-xs text-muted-foreground">
          {t('ws.records.sessionReports.overall.distribution.noData', locale)}
        </div>
      )}
    </div>
  )
}

function DistributionPie({ slices }: { slices: LocalizedSlice[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = echarts.init(el)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(el)

    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const colors = resolveCssColors()
    const data = slices
      .filter((slice) => slice.value > 0)
      .map((slice) => ({
        name: slice.displayLabel,
        value: slice.value,
      }))
    const total = data.reduce((sum, item) => sum + item.value, 0)
    const valueByName = new Map(data.map((item) => [item.name, item.value]))
    const option: EChartsOption = {
      color: colors,
      tooltip: {
        trigger: 'item',
        confine: true,
        formatter: (raw) => {
          const item = Array.isArray(raw) ? raw[0] : raw
          if (!isPieTooltipParam(item)) return ''
          const value = Number(item.value ?? 0)
          return `${item.marker ?? ''}${item.name ?? ''}: ${formatSliceValue(value, total)}`
        },
      },
      legend: {
        type: data.length > 4 ? 'scroll' : 'plain',
        bottom: 0,
        left: 'center',
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: '#737373', fontSize: 11 },
        formatter: (name: string) => {
          const value = valueByName.get(name) ?? 0
          return `${name} ${formatSliceValue(value, total)}`
        },
      },
      series: [
        {
          type: 'pie',
          radius: ['46%', '70%'],
          center: ['50%', '42%'],
          animation: false,
          avoidLabelOverlap: true,
          label: { show: false },
          emphasis: { disabled: true },
          data,
        },
      ],
    }
    chart.setOption(option, true)
  }, [slices])

  return <div ref={containerRef} className="mt-2 h-[180px] w-full" role="img" aria-hidden />
}

function resolveCssColors(): string[] {
  if (typeof document === 'undefined') return [...CHART_COLOR_FALLBACKS]

  const probe = document.createElement('span')
  probe.style.display = 'none'
  document.documentElement.appendChild(probe)

  const colors = CHART_COLOR_TOKENS.map((token, index) => {
    probe.style.color = `var(${token})`
    const resolved = getComputedStyle(probe).color.trim()
    return isEChartsColor(resolved) ? resolved : CHART_COLOR_FALLBACKS[index]
  })

  probe.remove()
  return colors
}

function isEChartsColor(value: string): boolean {
  return /^(#|rgba?\()/i.test(value)
}

function formatSliceValue(value: number, total: number): string {
  const percent = total > 0 ? (value / total) * 100 : 0
  return `${value.toLocaleString()} (${percent.toFixed(1)}%)`
}

function isPieTooltipParam(value: unknown): value is PieTooltipParam {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
