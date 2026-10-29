import type { EChartsOption } from 'echarts'
import type { Locale } from '@/context/locale-store'
import type { TrendType } from '@/models/call-report'
import type { CallMetricFormat, CallMetricLevel } from '@/models/call-report-overall'
import { formatDuration } from '@/utils/format-duration'
import { formatTrendXLabel, shouldShowTrendXLabel } from '@/utils/trend-chart-x-axis'
import { formatCallMetric } from './metric-format'

export type CallTrendChartMetric = {
  key: string
  name: string
  format: CallMetricFormat
  level: CallMetricLevel
}

export type CallTrendChartBucket = {
  label: string
  metrics: Array<{ key: string; value: number | null; format: CallMetricFormat }>
}

export type CallTrendAxisLabels = {
  count: string
  duration: string
  percent: string
}

const TOKENS = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'] as const
const FALLBACKS = ['#6b78d6', '#3ea6ad', '#54ad7e', '#d6a23e', '#d97089']

export function buildCallTrendChartOption(params: {
  metrics: CallTrendChartMetric[]
  buckets: CallTrendChartBucket[]
  trend: TrendType
  axisLabels: CallTrendAxisLabels
  locale: Locale
}): EChartsOption {
  const { metrics, buckets, trend, axisLabels, locale } = params
  const formats = new Set(metrics.map((metric) => metric.format))
  const { axes, indexByFormat } = buildAxes(formats, axisLabels, locale)
  const colors = resolveColors()
  const rightAxes = axes.filter((axis) => axis.position === 'right').length

  return {
    color: colors,
    grid: {
      left: 16,
      right: Math.max(16, rightAxes * 56),
      top: 20,
      bottom: 58,
      containLabel: true,
    },
    legend: {
      type: metrics.length > 6 ? 'scroll' : 'plain',
      bottom: 0,
      left: 'center',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: '#737373', fontSize: 12 },
      selected: Object.fromEntries(metrics.map((metric) => [metric.name, metric.level === 'primary'])),
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(0, 0, 0, 0.06)' } },
      formatter: (raw) => {
        const items = Array.isArray(raw) ? raw : [raw]
        if (items.length === 0) return ''
        const first = items[0] as { axisValue?: string; name?: string }
        const lines = items.map((item) => {
          const metric = metrics[item.seriesIndex ?? 0]
          const value = typeof item.value === 'number' ? item.value : null
          return `${item.marker ?? ''}${item.seriesName}: ${formatCallMetric(
            value,
            metric?.format ?? 'integer',
            locale,
          )}`
        })
        return [String(first.axisValue ?? first.name ?? ''), ...lines].join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: buckets.map((bucket) => bucket.label),
      axisTick: { alignWithLabel: true },
      axisLine: { lineStyle: { color: '#e5e5e5' } },
      axisLabel: {
        color: '#999999',
        fontSize: trend === 'half_hour' ? 9 : trend === 'hour' ? 10 : 11,
        interval: 0,
        formatter: (_value: string, index: number) =>
          shouldShowTrendXLabel(index, buckets.length, trend)
            ? formatTrendXLabel(buckets[index]?.label ?? '', index, trend)
            : '',
      },
    },
    yAxis: axes,
    series: metrics.map((metric, index) => {
      const common = {
        name: metric.name,
        yAxisIndex: indexByFormat[metric.format],
        data: buckets.map((bucket) =>
          bucket.metrics.find((item) => item.key === metric.key)?.value ?? null,
        ),
        color: colors[index % colors.length],
        emphasis: { disabled: true },
      }
      return metric.format === 'percent'
        ? { ...common, type: 'line' as const, connectNulls: false }
        : { ...common, type: 'bar' as const, itemStyle: { borderRadius: [2, 2, 0, 0] } }
    }),
  }
}

export function isCallTrendEmpty(
  metrics: CallTrendChartMetric[],
  buckets: CallTrendChartBucket[],
): boolean {
  return metrics.length === 0 || buckets.length === 0 || !buckets.some((bucket) =>
    bucket.metrics.some((item) => typeof item.value === 'number' && item.value !== 0),
  )
}

function buildAxes(
  formats: Set<CallMetricFormat>,
  labels: CallTrendAxisLabels,
  locale: Locale,
) {
  const axes: Array<Record<string, unknown> & { position: 'left' | 'right' }> = []
  const indexByFormat = {} as Record<CallMetricFormat, number>
  let rightOffset = 0
  const add = (format: CallMetricFormat, position: 'left' | 'right', formatter: (value: number) => string) => {
    indexByFormat[format] = axes.length
    axes.push({
      type: 'value',
      position,
      offset: position === 'right' ? rightOffset++ * 52 : 0,
      name: labels[format === 'integer' ? 'count' : format === 'percent' ? 'percent' : 'duration'],
      nameLocation: 'middle',
      nameRotate: position === 'left' ? 90 : -90,
      nameGap: 44,
      nameTextStyle: { color: '#999999', fontSize: 11 },
      axisLabel: { color: '#999999', fontSize: 11, formatter },
      splitLine: { show: position === 'left', lineStyle: { color: '#f0f0f0' } },
    })
  }
  if (formats.has('integer')) {
    add('integer', 'left', (value) => Math.round(value).toLocaleString(locale))
  }
  if (formats.has('duration_seconds')) {
    add('duration_seconds', formats.has('integer') ? 'right' : 'left', formatDuration)
  }
  if (formats.has('percent')) {
    add('percent', formats.size > 1 ? 'right' : 'left', (value) => `${(value * 100).toFixed(0)}%`)
  }
  return { axes, indexByFormat }
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
