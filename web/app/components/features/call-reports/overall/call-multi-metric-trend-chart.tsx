'use client'

import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Locale } from '@/context/locale-store'
import type { TrendType } from '@/models/call-report'
import {
  buildCallTrendChartOption,
  type CallTrendAxisLabels,
  type CallTrendChartBucket,
  type CallTrendChartMetric,
} from './build-call-trend-chart-option'

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

type Props = {
  metrics: CallTrendChartMetric[]
  buckets: CallTrendChartBucket[]
  trend: TrendType
  axisLabels: CallTrendAxisLabels
  locale: Locale
}

export function CallMultiMetricTrendChart({ metrics, buckets, trend, axisLabels, locale }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

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
    chart.setOption(buildCallTrendChartOption({ metrics, buckets, trend, axisLabels, locale }), true)
  }, [axisLabels, buckets, locale, metrics, trend])

  return <div ref={containerRef} className="h-[340px] w-full" role="img" aria-hidden />
}
