import {
  IconChartBar,
  IconChartHistogram,
  IconChartPie,
  IconGauge,
  type Icon,
} from '@tabler/icons-react'

export const DASHBOARD_ICON_OPTIONS = ['chart-bar', 'chart-histogram', 'chart-pie', 'gauge'] as const

const ICONS: Record<string, Icon> = {
  'chart-bar': IconChartBar,
  'chart-histogram': IconChartHistogram,
  'chart-pie': IconChartPie,
  gauge: IconGauge,
}

export function DashboardIcon({ name, size = 18, className }: { name: string; size?: number; className?: string }) {
  const IconComponent = ICONS[name] ?? IconChartBar
  return <IconComponent size={size} className={className} />
}
