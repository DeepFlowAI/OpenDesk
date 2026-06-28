'use client'

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { TrendType } from '@/models/session-report'
import {
  buildTrendChartOption,
  type TrendChartAxisLabels,
  type TrendChartBucket,
  type TrendChartMetric,
} from './build-trend-chart-option'

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])

type Props = {
  metrics: TrendChartMetric[]
  buckets: TrendChartBucket[]
  trend: TrendType
  axisLabels: TrendChartAxisLabels
  className?: string
}

export function MultiMetricTrendChart({
  metrics,
  buckets,
  trend,
  axisLabels,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = echarts.init(el)
    chartRef.current = chart

    const observer = new ResizeObserver(() => {
      chart.resize()
    })
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

    if (metrics.length === 0 || buckets.length === 0) {
      chart.clear()
      return
    }

    chart.setOption(
      buildTrendChartOption({ metrics, buckets, trend, axisLabels }),
      true,
    )
  }, [metrics, buckets, trend, axisLabels])

  return (
    <div
      ref={containerRef}
      className={className ?? 'h-[320px] w-full'}
      role="img"
      aria-hidden
    />
  )
}
