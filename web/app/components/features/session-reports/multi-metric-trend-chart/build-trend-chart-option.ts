import type { EChartsOption } from 'echarts'
import type { MetricFormat } from '@/models/session-report-overall'
import type { TrendType } from '@/models/session-report'
import { formatMetricValue, metricChartValue } from '../overall/metric-format'
import { formatDuration } from '@/utils/format-duration'
import { formatTrendXLabel, shouldShowTrendXLabel } from '@/utils/trend-chart-x-axis'

export type TrendChartMetric = {
  key: string
  name: string
  format: MetricFormat
  level: 'primary' | 'auxiliary'
}

export type TrendChartBucket = {
  label: string
  metrics: { key: string; value: number | null; format: MetricFormat }[]
}

export type TrendChartAxisLabels = {
  count: string
  duration: string
  percent: string
}

type SeriesMeta = {
  key: string
  format: MetricFormat
}

const CHART_COLOR_TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'] as const

/** Light-mode fallbacks aligned with design-system chart palette (low-chroma hues). */
const CHART_COLOR_FALLBACKS = ['#6b78d6', '#3ea6ad', '#54ad7e', '#d6a23e', '#d97089']

/** Resolve CSS chart tokens to rgb/rgba strings ECharts canvas can render. */
function resolveCssColors(): string[] {
  if (typeof document === 'undefined') return [...CHART_COLOR_FALLBACKS]

  const probe = document.createElement('span')
  probe.style.display = 'none'
  document.documentElement.appendChild(probe)

  const colors = CHART_COLOR_TOKENS.map((token, index) => {
    probe.style.color = `var(${token})`
    const resolved = getComputedStyle(probe).color.trim()
    return resolved && resolved !== 'rgba(0, 0, 0, 0)' ? resolved : CHART_COLOR_FALLBACKS[index]
  })

  probe.remove()
  return colors
}

function bucketValue(
  bucket: TrendChartBucket,
  key: string,
): number {
  const found = bucket.metrics.find((m) => m.key === key)
  return metricChartValue(found?.value ?? null)
}

function yAxisNameConfig(position: 'left' | 'right', label: string) {
  return {
    name: label,
    nameLocation: 'middle' as const,
    nameRotate: position === 'left' ? 90 : -90,
    nameGap: 44,
    nameTextStyle: { color: '#999999', fontSize: 11 },
  }
}

function buildYAxes(
  formats: Set<MetricFormat>,
  axisLabels: TrendChartAxisLabels,
): { yAxis: EChartsOption['yAxis']; formatToAxisIndex: Record<MetricFormat, number> } {
  const yAxis: NonNullable<EChartsOption['yAxis']> = []
  const formatToAxisIndex = {} as Record<MetricFormat, number>
  let rightAxisCount = 0

  const nextRightOffset = () => {
    const offset = rightAxisCount * 52
    rightAxisCount += 1
    return offset
  }

  if (formats.has('integer')) {
    formatToAxisIndex.integer = yAxis.length
    yAxis.push({
      type: 'value',
      position: 'left',
      ...yAxisNameConfig('left', axisLabels.count),
      axisLabel: {
        color: '#999999',
        fontSize: 11,
        formatter: (value: number) => Math.round(value).toLocaleString(),
      },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    })
  }

  if (formats.has('duration_seconds')) {
    const onRight = formats.has('integer')
    formatToAxisIndex.duration_seconds = yAxis.length
    yAxis.push({
      type: 'value',
      position: onRight ? 'right' : 'left',
      offset: onRight ? nextRightOffset() : 0,
      ...yAxisNameConfig(onRight ? 'right' : 'left', axisLabels.duration),
      axisLabel: {
        color: '#999999',
        fontSize: 11,
        formatter: (value: number) => formatDuration(value),
      },
      splitLine: { show: !onRight, lineStyle: { color: '#f0f0f0' } },
    })
    if (onRight) {
      // offset already consumed
    }
  }

  if (formats.has('percent')) {
    const onRight = formats.has('integer') || formats.has('duration_seconds')
    formatToAxisIndex.percent = yAxis.length
    yAxis.push({
      type: 'value',
      position: onRight ? 'right' : 'left',
      offset: onRight ? nextRightOffset() : 0,
      ...yAxisNameConfig(onRight ? 'right' : 'left', axisLabels.percent),
      axisLabel: {
        color: '#999999',
        fontSize: 11,
        formatter: (value: number) => `${(value * 100).toFixed(0)}%`,
      },
      splitLine: { show: !onRight, lineStyle: { color: '#f0f0f0' } },
    })
  }

  return { yAxis, formatToAxisIndex }
}

export function buildTrendChartOption(params: {
  metrics: TrendChartMetric[]
  buckets: TrendChartBucket[]
  trend: TrendType
  axisLabels: TrendChartAxisLabels
}): EChartsOption {
  const { metrics, buckets, trend, axisLabels } = params
  const bucketCount = buckets.length
  const xLabels = buckets.map((b) => b.label)
  const formats = new Set(metrics.map((m) => m.format))
  const { yAxis, formatToAxisIndex } = buildYAxes(formats, axisLabels)
  const colors = resolveCssColors()

  const rightAxisCount = (yAxis as { position?: string }[]).filter((a) => a.position === 'right').length
  const seriesMeta: SeriesMeta[] = []

  const series = metrics.map((metric, index) => {
    seriesMeta.push({ key: metric.key, format: metric.format })
    const base = {
      name: metric.name,
      yAxisIndex: formatToAxisIndex[metric.format],
      emphasis: { disabled: true },
      data: buckets.map((bucket) => bucketValue(bucket, metric.key)),
      color: colors[index % colors.length],
    }
    if (metric.format === 'percent') {
      return { ...base, type: 'line' as const }
    }
    return {
      ...base,
      type: 'bar' as const,
      itemStyle: { borderRadius: [2, 2, 0, 0] },
    }
  })

  const legendSelected = Object.fromEntries(
    metrics.map((m) => [m.name, m.level === 'primary']),
  )

  return {
    color: colors,
    grid: {
      left: 16,
      right: Math.max(16, rightAxisCount * 56),
      top: 20,
      bottom: 56,
      containLabel: true,
    },
    legend: {
      type: metrics.length > 6 ? 'scroll' : 'plain',
      bottom: 0,
      left: 'center',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#737373', fontSize: 12 },
      selectedMode: true,
      data: metrics.map((m) => m.name),
      selected: legendSelected,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
        shadowStyle: { color: 'rgba(0, 0, 0, 0.06)' },
      },
      confine: true,
      formatter: (raw) => {
        const items = Array.isArray(raw) ? raw : [raw]
        if (items.length === 0) return ''
        const first = items[0] as { axisValue?: string; name?: string }
        const header = String(first.axisValue ?? first.name ?? '')
        const lines = items.map((item) => {
          const meta = seriesMeta[item.seriesIndex ?? 0]
          const formatted = formatMetricValue(
            typeof item.value === 'number' ? item.value : Number(item.value),
            meta?.format ?? 'integer',
          )
          return `${item.marker ?? ''}${item.seriesName}: ${formatted}`
        })
        return [header, ...lines].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: xLabels,
      axisTick: { alignWithLabel: true },
      axisLine: { lineStyle: { color: '#e5e5e5' } },
      axisLabel: {
        color: '#999999',
        fontSize: trend === 'half_hour' ? 9 : trend === 'hour' ? 10 : 11,
        interval: 0,
        formatter: (value: string, index: number) => {
          if (!shouldShowTrendXLabel(index, bucketCount, trend)) return ''
          return formatTrendXLabel(value, index, trend)
        },
      },
    },
    yAxis,
    series,
  }
}

export function isTrendChartEmpty(
  metrics: TrendChartMetric[],
  buckets: TrendChartBucket[],
): boolean {
  if (metrics.length === 0 || buckets.length === 0) return true
  return buckets.every((bucket) =>
    metrics.every((metric) => bucketValue(bucket, metric.key) === 0),
  )
}
