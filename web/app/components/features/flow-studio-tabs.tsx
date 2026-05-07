'use client'

import Link from 'next/link'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

export type FlowStudioTab = 'routing-rules' | 'voice-flows'

type FlowStudioTabsProps = {
  active: FlowStudioTab
}

export function FlowStudioTabs({ active }: FlowStudioTabsProps) {
  const { locale } = useLocaleStore()

  const tabClass = (isActive: boolean) =>
    cn(
      'flex h-8 items-center justify-center rounded-md px-4 text-sm transition-all',
      isActive ? 'bg-white font-medium text-foreground shadow-sm' : 'font-normal text-muted-foreground hover:text-foreground/80'
    )

  return (
    <div className="inline-flex h-10 items-center gap-1 rounded-lg bg-muted p-1">
      <Link href="/flow-studio/routing-rules" className={tabClass(active === 'routing-rules')}>
        {t('fs.tab.routingRules', locale)}
      </Link>
      <Link href="/flow-studio/voice-flows" className={tabClass(active === 'voice-flows')}>
        {t('fs.tab.voiceFlows', locale)}
      </Link>
    </div>
  )
}
