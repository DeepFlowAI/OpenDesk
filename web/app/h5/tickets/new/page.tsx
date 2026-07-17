'use client'

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { toast } from 'sonner'

import { H5TicketShell } from '@/app/components/features/ticket/h5-ticket-shell'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { buildH5TicketDetailUrl, buildH5TicketListUrl, listContextFromChildParams } from '@/lib/h5-ticket-navigation'
import { hasPermission } from '@/utils/permissions'
import { TicketCreateForm } from '@/app/workspace/tickets/ticket-form-modal'

export default function H5NewTicketPageWrapper() {
  return <Suspense><H5NewTicketPage /></Suspense>
}

function H5NewTicketPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const user = useAuthStore((state) => state.user)
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const context = listContextFromChildParams(searchParams)
  const listUrl = buildH5TicketListUrl(context)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const requestLeave = () => {
    if (dirty) setConfirmOpen(true)
    else router.push(listUrl)
  }

  if (!hasPermission(user, 'ticket.workspace.create')) {
    return (
      <H5TicketShell title={isZh ? '新建工单' : 'Create ticket'} onBack={() => router.push(listUrl)}>
        <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
          {isZh ? '无权新建工单' : 'You do not have permission to create tickets'}
        </div>
      </H5TicketShell>
    )
  }

  return (
    <>
      <H5TicketShell
        title={isZh ? '新建工单' : 'Create ticket'}
        onBack={requestLeave}
        backLabel={isZh ? '返回工单列表' : 'Back to ticket list'}
        contentClassName="overflow-hidden"
      >
        <TicketCreateForm
          columnsPerRowOverride={1}
          labelPositionOverride="top"
          className="h-full"
          bodyClassName="p-4"
          footerClassName="grid grid-cols-2 gap-3 border-t border-border px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 [&>button]:h-11 [&>button]:w-full"
          submitLabel={isZh ? '创建' : 'Create'}
          submittingLabel={isZh ? '创建中…' : 'Creating…'}
          cancelLabel={isZh ? '取消' : 'Cancel'}
          onCancel={requestLeave}
          onDirtyChange={setDirty}
          onSuccess={(ticket) => {
            setDirty(false)
            toast.success(isZh ? '工单已创建' : 'Ticket created')
            router.replace(buildH5TicketDetailUrl(ticket.id, context))
          }}
          onError={() => toast.error(isZh ? '操作失败，请重试' : 'Operation failed. Please try again')}
        />
      </H5TicketShell>

      <ConfirmDialog
        open={confirmOpen}
        title={isZh ? '放弃未保存的内容？' : 'Discard unsaved changes?'}
        message={isZh ? '当前内容尚未保存，返回后将丢失已填写内容。' : 'Your changes have not been saved. Going back will discard them.'}
        cancelLabel={isZh ? '继续编辑' : 'Continue editing'}
        confirmLabel={isZh ? '放弃并返回' : 'Discard and go back'}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => router.push(listUrl)}
      />
    </>
  )
}
