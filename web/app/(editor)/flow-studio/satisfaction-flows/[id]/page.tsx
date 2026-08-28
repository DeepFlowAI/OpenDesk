'use client'

import { useParams } from 'next/navigation'
import { SatisfactionFlowEditorPage } from '@/app/components/features/satisfaction-flow/editor'

export default function EditSatisfactionFlowPage() {
  const params = useParams<{ id: string }>()
  const id = Number.parseInt(params.id, 10)
  if (Number.isNaN(id)) return <div className="p-6 text-sm text-destructive">无效的满意度流程 ID</div>
  return <SatisfactionFlowEditorPage id={id} />
}
