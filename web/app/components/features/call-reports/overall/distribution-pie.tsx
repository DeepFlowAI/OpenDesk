'use client'

import { useEffect, useMemo, useRef } from 'react'
import * as echarts from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import type { Locale } from '@/context/locale-store'
import type { CallDistributionSlice } from '@/models/call-report-overall'

echarts.use([PieChart, LegendComponent, TooltipComponent, CanvasRenderer])

const TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'] as const
const FALLBACKS = ['#6b78d6', '#3ea6ad', '#54ad7e', '#d6a23e', '#d97089']

type Props = {
  label: string
  locale: Locale
  otherLabel: string
  slices: Array<CallDistributionSlice & { displayLabel: string }>
}

export function CallDistributionPie({ label, locale, otherLabel, slices }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const chartSlices = useMemo(() => compactSlices(slices, otherLabel), [otherLabel, slices])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const chart = echarts.init(element)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(element)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const total = chartSlices.reduce((sum, slice) => sum + slice.value, 0)
    const values = new Map(chartSlices.map((slice) => [slice.displayLabel, slice.value]))
    const option: EChartsOption = {
      color: resolveColors(),
      tooltip: {
        trigger: 'item',
        confine: true,
        formatter: (raw) => {
          const item = Array.isArray(raw) ? raw[0] : raw
          if (!isTooltipItem(item)) return ''
          const value = Number(item.value ?? 0)
          return `${item.marker ?? ''}${item.name ?? ''}: ${formatSlice(value, total, locale)}`
        },
      },
      legend: {
        type: chartSlices.length > 4 ? 'scroll' : 'plain',
        bottom: 0,
        left: 'center',
        itemWidth: 9,
        itemHeight: 9,
        textStyle: { color: '#737373', fontSize: 11 },
        formatter: (name: string) => `${name} ${formatSlice(values.get(name) ?? 0, total, locale)}`,
      },
      series: [{
        type: 'pie',
        radius: ['40%', '62%'],
        center: ['50%', '38%'],
        animation: false,
        label: { show: false },
        emphasis: { disabled: true },
        data: chartSlices.map((slice) => ({ name: slice.displayLabel, value: slice.value })),
      }],
    }
    chart.setOption(option, true)
  }, [chartSlices, locale])

  return <div ref={containerRef} className="h-[160px] w-full" role="img" aria-label={label} />
}

function compactSlices(slices: Props['slices'], otherLabel: string): Props['slices'] {
  const populated = slices.filter((slice) => slice.value > 0)
  if (populated.length <= 8) return populated
  const head = populated.slice(0, 8)
  const tailValue = populated.slice(8).reduce((sum, slice) => sum + slice.value, 0)
  const existingOther = head.find((slice) => slice.key === 'other')
  if (existingOther) {
    return head.map((slice) => slice.key === 'other'
      ? { ...slice, value: slice.value + tailValue }
      : slice)
  }
  return [
    ...head,
    {
      key: 'other',
      label: 'other',
      displayLabel: populated.find((slice) => slice.key === 'other')?.displayLabel ?? otherLabel,
      value: tailValue,
    },
  ]
}

function resolveColors(): string[] {
  if (typeof document === 'undefined') return FALLBACKS
  const probe = document.createElement('span')
  probe.style.display = 'none'
  document.documentElement.appendChild(probe)
  const colors = TOKENS.map((token, index) => {
    probe.style.color = `var(${token})`
    const value = getComputedStyle(probe).color.trim()
    return /^(#|rgba?\()/i.test(value) ? value : FALLBACKS[index]
  })
  probe.remove()
  return colors
}

function formatSlice(value: number, total: number, locale: Locale): string {
  const percent = total ? value / total : 0
  return `${value.toLocaleString(locale)} (${new Intl.NumberFormat(locale, {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(percent)})`
}

function isTooltipItem(value: unknown): value is { marker?: string; name?: string; value?: number } {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
