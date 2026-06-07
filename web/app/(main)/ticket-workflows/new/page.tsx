'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useCreateTicketWorkflow } from '@/service/use-ticket-workflows'

export default function NewTicketWorkflowPage() {
  const router = useRouter()
  const create = useCreateTicketWorkflow()

  useEffect(() => {
    if (create.isPending || create.isSuccess) return
    create.mutate(
      { name: '未命名流程', enabled: false },
      {
        onSuccess: (workflow) => router.replace(`/ticket-workflows/${workflow.id}`),
        onError: () => router.replace('/ticket-workflows'),
      },
    )
  }, [create, router])

  return <p className="text-sm text-muted-foreground">正在创建流程...</p>
}
