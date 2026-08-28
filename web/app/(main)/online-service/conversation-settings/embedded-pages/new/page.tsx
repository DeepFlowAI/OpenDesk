'use client'

import { EmbeddedPageForm } from '@/app/components/features/conversation-settings/embedded-page-form'

const BASE_PATH = '/online-service/conversation-settings/embedded-pages'

export default function NewEmbeddedPagePage() {
  return (
    <EmbeddedPageForm
      location="chat_auxiliary"
      basePath={BASE_PATH}
      backPath="/online-service/conversation-settings"
    />
  )
}
