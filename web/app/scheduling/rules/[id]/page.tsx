'use client'

import { use } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useRuleSet } from '@/service/use-scheduling-rules'
import { RuleSetForm } from '@/app/components/features/scheduling/rules/rule-set-form'

export default function SchedulingRuleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const { locale } = useLocaleStore()
  const { data: ruleSet, isLoading, isError } = useRuleSet(Number(id))

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
        {t('scheduling.rules.loading', locale)}
      </div>
    )
  }
  if (isError || !ruleSet) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
        {t('scheduling.rules.notFound', locale)}
      </div>
    )
  }
  return <RuleSetForm key={ruleSet.id} ruleSet={ruleSet} />
}
