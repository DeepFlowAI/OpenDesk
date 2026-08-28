'use client'

import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'

import { EmbeddedCallClient } from '@/app/embedded/call/embedded-call-client'


function EmbeddedCallRoute() {
  const searchParams = useSearchParams()
  return (
    <EmbeddedCallClient
      integrationKey={searchParams.get('integrationKey') || ''}
      instanceId={searchParams.get('instanceId') || ''}
      protocolVersion={searchParams.get('v') || ''}
      initialExpanded={searchParams.get('expanded') !== '0'}
      requestedLocale={searchParams.get('locale') || undefined}
      requestedTheme={searchParams.get('theme') || undefined}
    />
  )
}

export default function EmbeddedCallPage() {
  return (
    <Suspense fallback={null}>
      <EmbeddedCallRoute />
    </Suspense>
  )
}
