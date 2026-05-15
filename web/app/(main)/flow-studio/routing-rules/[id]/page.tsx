'use client'

import { useParams } from 'next/navigation'
import { RoutingRuleForm } from '@/app/components/features/routing-rule-form'

export default function EditRoutingRulePage() {
  const params = useParams()
  const raw = params.id as string
  const id = Number.parseInt(raw, 10)
  if (Number.isNaN(id)) {
    return <p className="text-sm text-red-600">Invalid id</p>
  }
  return <RoutingRuleForm ruleId={id} />
}
