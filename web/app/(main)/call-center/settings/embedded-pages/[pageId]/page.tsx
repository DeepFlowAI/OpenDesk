'use client'

import { useParams } from 'next/navigation'
import { EmbeddedPageForm } from '@/app/components/features/conversation-settings/embedded-page-form'

const BASE_PATH = '/call-center/settings/embedded-pages'

export default function EditScreenPopEmbeddedPagePage() {
  const params = useParams()
  const id = Number.parseInt(params.pageId as string, 10)
  if (Number.isNaN(id)) {
    return <p className="text-sm text-destructive">Invalid id</p>
  }
  return (
    <EmbeddedPageForm
      pageId={id}
      location="call_screen_pop"
      basePath={BASE_PATH}
      backPath="/call-center/settings"
    />
  )
}
