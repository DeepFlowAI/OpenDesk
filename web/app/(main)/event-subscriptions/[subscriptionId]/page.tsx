'use client'

import { useParams } from 'next/navigation'
import { SubscriptionForm } from '@/app/components/features/event-subscriptions/subscription-form'

export default function EditEventSubscriptionPage() {
  const params = useParams<{ subscriptionId: string }>()
  return <SubscriptionForm subscriptionId={params.subscriptionId} />
}
