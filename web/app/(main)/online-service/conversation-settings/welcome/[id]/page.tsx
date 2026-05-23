'use client'

import { useParams } from 'next/navigation'
import { WelcomeMessageRuleForm } from '@/app/components/features/welcome-message-rule-form'

export default function EditWelcomeMessageRulePage() {
  const params = useParams()
  const id = Number.parseInt(params.id as string, 10)
  if (Number.isNaN(id)) {
    return <p className="text-sm text-destructive">Invalid id</p>
  }
  return <WelcomeMessageRuleForm ruleId={id} />
}
