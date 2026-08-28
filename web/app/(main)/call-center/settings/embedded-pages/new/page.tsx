'use client'

import { EmbeddedPageForm } from '@/app/components/features/conversation-settings/embedded-page-form'

const BASE_PATH = '/call-center/settings/embedded-pages'

export default function NewScreenPopEmbeddedPagePage() {
  return (
    <EmbeddedPageForm
      location="call_screen_pop"
      basePath={BASE_PATH}
      backPath="/call-center/settings"
    />
  )
}
