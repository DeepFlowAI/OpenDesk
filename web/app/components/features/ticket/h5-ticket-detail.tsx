'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { HTTPError } from 'ky'

import { H5TicketActivity } from '@/app/components/features/ticket/h5-ticket-activity'
import { H5TicketDetailForm } from '@/app/components/features/ticket/h5-ticket-detail-form'
import { H5TicketShell } from '@/app/components/features/ticket/h5-ticket-shell'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { buildH5TicketListUrl, listContextFromChildParams } from '@/lib/h5-ticket-navigation'
import { cn } from '@/lib/utils'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useOrganization } from '@/service/use-organizations'
import { useTicket, useFormLayoutByScene, useInteractionRules } from '@/service/use-tickets'
import { useUser } from '@/service/use-users'
import { hasPermission } from '@/utils/permissions'

export function H5TicketDetail() {
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const ticketId = Number(params.ticketId)
  const user = useAuthStore((state) => state.user)
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const listUrl = buildH5TicketListUrl(listContextFromChildParams(searchParams))
  const [primaryTab, setPrimaryTab] = useState<'info' | 'activity'>('info')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [hasEditable, setHasEditable] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const ticketQuery = useTicket(ticketId)
  const ticket = ticketQuery.data
  const layoutQuery = useFormLayoutByScene('ticket_detail')
  const layout = layoutQuery.data
  const { data: rulesData } = useInteractionRules(layout?.id)
  const { data: relatedUser } = useUser(ticket?.user_id ?? 0)
  const { data: relatedOrganization } = useOrganization(relatedUser?.organization_id ?? 0)
  const fieldLocale = isZh ? 'zh' : 'en'
  const ticketFields = useUnifiedFields({ domain: 'ticket', include_metadata: true, locale: fieldLocale })
  const userFields = useUnifiedFields({ domain: 'user', include_metadata: false, locale: fieldLocale })
  const organizationFields = useUnifiedFields({ domain: 'organization', include_metadata: false, locale: fieldLocale })
  const sharedFields = useUnifiedFields({ domain: 'shared_pool', include_metadata: false, locale: fieldLocale })
  const allFields = useMemo(() => [
    ...(ticketFields.data?.items ?? []),
    ...(userFields.data?.items ?? []),
    ...(organizationFields.data?.items ?? []),
    ...(sharedFields.data?.items ?? []),
  ], [organizationFields.data, sharedFields.data, ticketFields.data, userFields.data])
  const rules = useMemo(() => (rulesData?.items ?? []).filter((rule) => rule.is_enabled).sort((a, b) => a.sort_order - b.sort_order), [rulesData])
  const canEdit = hasPermission(user, 'ticket.workspace.edit')
  const canComment = hasPermission(user, 'ticket.workspace.comment')
  const formConfigLoading = layoutQuery.isLoading
    || ticketFields.isLoading
    || userFields.isLoading
    || organizationFields.isLoading
    || sharedFields.isLoading

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const requestLeave = () => dirty ? setConfirmOpen(true) : router.push(listUrl)

  if (ticketQuery.isLoading) {
    return <H5TicketShell title={isZh ? '工单详情' : 'Ticket details'} onBack={() => router.push(listUrl)}><DetailState text={isZh ? '加载中…' : 'Loading…'} /></H5TicketShell>
  }

  if (ticketQuery.isError || !ticket) {
    const status = ticketQuery.error instanceof HTTPError ? ticketQuery.error.response.status : 0
    const text = status === 403
      ? (isZh ? '无权查看该工单' : 'You do not have access to this ticket')
      : status === 404
        ? (isZh ? '工单不存在' : 'Ticket not found')
        : (isZh ? '加载失败，请重试' : 'Failed to load. Please try again')
    return <H5TicketShell title={isZh ? '工单详情' : 'Ticket details'} onBack={() => router.push(listUrl)}><DetailState text={text} action={() => router.push(listUrl)} actionLabel={isZh ? '返回工单列表' : 'Back to ticket list'} /></H5TicketShell>
  }

  return (
    <>
      <H5TicketShell
        title={ticket.ticket_number ? `#${ticket.ticket_number.replace(/^#/, '')}` : ticket.title}
        onBack={requestLeave}
        backLabel={isZh ? '返回工单列表' : 'Back to ticket list'}
        contentClassName="overflow-hidden"
        footer={primaryTab === 'info' && canEdit && hasEditable ? (
          <div className="shrink-0 border-t border-border bg-background px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3">
            <button type="submit" form="h5-ticket-detail-form" disabled={saving || !dirty} className="h-11 w-full rounded-lg bg-primary text-sm font-medium text-primary-foreground disabled:opacity-40">
              {saving ? (isZh ? '保存中…' : 'Saving…') : (isZh ? '保存' : 'Save')}
            </button>
          </div>
        ) : undefined}
      >
        <div className="flex h-full min-h-0 flex-col">
          <div className="grid h-[52px] shrink-0 grid-cols-2 border-b border-border">
            {(['info', 'activity'] as const).map((tab) => (
              <button key={tab} type="button" onClick={() => setPrimaryTab(tab)} className={cn('border-b-2 text-sm', primaryTab === tab ? 'border-primary font-semibold' : 'border-transparent text-muted-foreground')}>
                {tab === 'info' ? (isZh ? '工单信息' : 'Ticket info') : (isZh ? '动态' : 'Activity')}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className={cn('min-h-full', primaryTab !== 'info' && 'hidden')}>
              {formConfigLoading ? <DetailState text={isZh ? '加载中…' : 'Loading…'} /> : <H5TicketDetailForm
                ticket={ticket}
                layout={layout}
                rules={rules}
                fields={allFields}
                relatedUser={relatedUser as unknown as Record<string, unknown>}
                relatedOrganization={relatedOrganization as unknown as Record<string, unknown>}
                canEdit={canEdit}
                isZh={isZh}
                onDirtyChange={setDirty}
                onSavingChange={setSaving}
                onEditableChange={setHasEditable}
              />}
            </div>
            <div className={cn('h-full min-h-0', primaryTab !== 'activity' && 'hidden')}>
              <H5TicketActivity ticketId={ticketId} canComment={canComment} isZh={isZh} />
            </div>
          </div>
        </div>
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

function DetailState({ text, action, actionLabel }: { text: string; action?: () => void; actionLabel?: string }) {
  return <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center"><p className="text-sm text-muted-foreground">{text}</p>{action && actionLabel && <button type="button" onClick={action} className="h-10 rounded-lg border border-border px-4 text-sm font-medium">{actionLabel}</button>}</div>
}
