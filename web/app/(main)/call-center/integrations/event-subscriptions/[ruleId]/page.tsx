'use client'

import { useParams } from 'next/navigation'

import { CallEventRuleForm } from '@/app/components/features/call-center/call-event-rule-form'


export default function CallEventSubscriptionRuleDetailPage() {
  const params = useParams<{ ruleId: string }>()
  return <CallEventRuleForm key={params.ruleId} ruleId={params.ruleId} />
}
