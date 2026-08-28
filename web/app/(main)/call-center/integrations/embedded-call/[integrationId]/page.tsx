'use client'

import { useParams } from 'next/navigation'

import { EmbeddedCallIntegrationForm } from '@/app/components/features/call-center/embedded-call-integration-form'


export default function EmbeddedCallIntegrationDetailPage() {
  const params = useParams<{ integrationId: string }>()
  return <EmbeddedCallIntegrationForm integrationId={params.integrationId} />
}
