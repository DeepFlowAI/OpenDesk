'use client'
/**
 * New voice flow: create an empty flow on the server, then redirect into the
 * editor for the freshly-created id. The detail page handles the rest.
 */
import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { useCreateVoiceFlow } from '@/service/use-voice-flows'
import { leaveVoiceFlowEditor } from '@/utils/voice-flow-editor-navigation'

export default function NewVoiceFlowPage() {
  const router = useRouter()
  const create = useCreateVoiceFlow()
  const calledOnce = useRef(false)

  useEffect(() => {
    if (calledOnce.current) return
    calledOnce.current = true
    ;(async () => {
      try {
        const flow = await create.mutateAsync({ name: '未命名语音流程' })
        router.replace(`/flow-studio/voice-flows/${flow.id}`)
      } catch {
        toast.error('创建失败')
        leaveVoiceFlowEditor(router, 'replace')
      }
    })()
    // We intentionally only run this once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">正在创建语音流程...</p>
    </div>
  )
}
