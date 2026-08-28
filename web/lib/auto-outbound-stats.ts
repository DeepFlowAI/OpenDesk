import type { Locale } from '@/context/locale-store'
import type { AutoOutboundResultDistribution } from '@/models/auto-outbound-task'
import { t } from '@/utils/i18n'

export type ResultDistributionChartItem = { label: string; count: number }

// The stats API returns result_distribution as a mode-specific object
// (ivr exits / bot intents / agent breakdown). Normalize it to label-count
// items for the bar chart.
export function mapResultDistributionItems(
  executionMode: string,
  dist: AutoOutboundResultDistribution | undefined,
  locale: Locale,
): ResultDistributionChartItem[] {
  if (!dist || typeof dist !== 'object' || Array.isArray(dist)) return []

  if (executionMode === 'ivr') {
    const exits = 'exits' in dist ? dist.exits : undefined
    return Object.entries(exits ?? {}).map(([label, count]) => ({ label, count }))
  }

  if (executionMode === 'bot') {
    if (!('intents' in dist)) return []
    const items = Object.entries(dist.intents ?? {}).map(([label, count]) => ({ label, count }))
    if ((dist.handoff_count ?? 0) > 0) {
      items.push({ label: t('ws.autoOutbound.stats.handoffItem', locale), count: dist.handoff_count })
    }
    return items
  }

  const agents = 'agents' in dist ? dist.agents : undefined
  return (agents ?? []).map((agent) => ({
    label: t('ws.autoOutbound.stats.agentItem', locale, { id: agent.agent_id }),
    count: agent.answered,
  }))
}
