'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { defaultSatisfactionDraft } from '@/models/satisfaction-flow'
import { useCreateSatisfactionFlow } from '@/service/use-satisfaction-flows'

export default function NewSatisfactionFlowPage() {
  const router = useRouter()
  const create = useCreateSatisfactionFlow()
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    void create.mutateAsync(defaultSatisfactionDraft()).then((flow) => {
      router.replace(`/flow-studio/satisfaction-flows/${flow.id}`)
    }).catch(() => {
      toast.error('满意度流程创建失败')
      router.replace('/flow-studio/satisfaction-flows')
    })
  }, [create, router])
  return <div className="grid h-screen place-items-center text-sm text-muted-foreground">正在创建满意度流程...</div>
}
