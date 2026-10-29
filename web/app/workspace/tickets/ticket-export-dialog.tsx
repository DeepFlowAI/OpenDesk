'use client'

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { toast } from 'sonner'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { useAuthStore } from '@/context/auth-store'
import { hasAllPermissions } from '@/utils/permissions'
import { t } from '@/utils/i18n'
import { useTicketExportConfig } from '@/service/use-ticket-export'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { authKeys } from '@/service/use-auth'
import { createExportTask, exportErrorCode, exportKeys } from '@/service/use-export-tasks'
import { exportColumnOrder, exportFieldUid, orderedExportSelection, type TicketExportSource, type TicketExportConfig } from '@/models/ticket-export'
import type { ExportSubmission } from '@/models/export-task'
import { TicketExportScope } from '@/app/workspace/tickets/ticket-export-scope'
import { TicketExportFields } from '@/app/workspace/tickets/ticket-export-fields'

export function TicketExportDialog({ source, onClose }: { source: TicketExportSource; onClose: () => void }) {
  const query = useTicketExportConfig(source)
  const [busy, setBusy] = useState(false)
  return <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose() }}>
    <DialogContent className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-[720px]" showCloseButton={!busy}>
      <div className="p-6"><DialogTitle>{t('ticketExport.title', source.language)}</DialogTitle>
        <DialogDescription className="mt-2">{t('ticketExport.rangeNote', source.language)}</DialogDescription></div>
      {query.data ? <ExportConfiguration source={source} config={query.data} onClose={onClose} setBusy={setBusy} /> :
        <div className="p-6" role={query.isError ? 'alert' : 'status'}>{t(query.isError ? 'ticketExport.loadFailed' : 'ticketExport.loading', source.language)}
          {query.isError && <Button variant="secondary" onClick={() => void query.refetch()}>{t('exports.refresh', source.language)}</Button>}
        </div>}
    </DialogContent>
  </Dialog>
}

function ExportConfiguration({ source, config, onClose, setBusy }: {
  source: TicketExportSource; config: TicketExportConfig; onClose: () => void; setBusy: (busy: boolean) => void
}) {
  const locale = source.language
  const defaults = exportColumnOrder(source.columns, config.prepared.fields)
  const [selected, setSelected] = useState(defaults)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [revoked, setRevoked] = useState(false)
  const submission = useRef<ExportSubmission | null>(null)
  const busy = useRef(false)
  const user = useAuthStore((state) => state.user)
  const permitted = !revoked && hasAllPermissions(user, ['ticket.workspace.view', 'ticket.workspace.export'])
  const current = useUnifiedFields({ domain: 'ticket', include_metadata: true, locale })
  const valid = new Map((current.data?.items ?? config.prepared.fields).filter((field) => field.status === 'active').map((field) => [exportFieldUid(field), field]))
  const invalid = config.prepared.fields.filter((field) => selected.includes(exportFieldUid(field)) && (
    !valid.has(exportFieldUid(field)) || valid.get(exportFieldUid(field))?.field_type !== field.field_type || valid.get(exportFieldUid(field))?.slot_column !== field.slot_column))
  const qc = useQueryClient()
  const router = useRouter()
  const submit = async () => {
    if (busy.current || !permitted) return
    busy.current = true
    setPending(true); setBusy(true); setError('')
    submission.current ??= { idempotency_key: crypto.randomUUID(), kind: 'ticket', language: locale, timezone: source.timezone,
      config: { prepared: config.token, signature: config.signature, fields: orderedExportSelection(selected, defaults, config.prepared.fields) } }
    try {
      await createExportTask(submission.current)
      void qc.invalidateQueries({ queryKey: exportKeys })
      toast.success(t('ticketExport.created', locale), {
        classNames: { actionButton: 'bg-transparent! text-inherit! border! border-current! hover:opacity-75' },
        action: { label: t('ticketExport.viewTasks', locale), onClick: () => router.push('/workspace/exports') },
      })
      onClose()
    } catch (failure) {
      const unknown = !(failure instanceof HTTPError) || failure.response.status >= 500
      setUncertain(unknown)
      if (!unknown) submission.current = null
      const code = await exportErrorCode(failure)
      if (code === 'permission_lost') {
        setRevoked(true)
        void qc.invalidateQueries({ queryKey: authKeys.currentUser })
      }
      setError(unknown ? t('ticketExport.uncertain', locale) : t(`exports.error.${code}`, locale))
      if (code === 'configuration_invalid') void current.refetch()
    } finally {
      busy.current = false; setPending(false); setBusy(submission.current !== null)
    }
  }
  const fields = config.prepared.fields
  return <>
    <div className="space-y-6 overflow-y-auto px-6 pb-6">
      <TicketExportScope config={config} source={source} />
      {!permitted && <p role="alert" className="text-destructive">{t('exports.error.permission_lost', locale)}</p>}
      {config.count > 50000 && <p role="alert" className="text-destructive">{t('exports.error.row_limit', locale)}</p>}
      {invalid.length > 0 && <div role="alert" className="text-destructive">{t('ticketExport.invalid', locale)}{invalid.map((field) => <p key={exportFieldUid(field)}>{field.name}<Button disabled={pending || uncertain || exportFieldUid(field) === 'key:ticket_number'} variant="ghost" onClick={() => setSelected(selected.filter((uid) => uid !== exportFieldUid(field)))}>{t('ticketExport.remove', locale)}</Button></p>)}</div>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      <TicketExportFields fields={fields} selected={selected} defaults={defaults.filter((uid) => valid.has(uid))} onChange={setSelected} language={locale} disabled={pending || uncertain} />
    </div>
    <div className="flex shrink-0 justify-end gap-2 border-t border-border p-4">
      <Button variant="secondary" disabled={pending || uncertain} onClick={onClose}>{t('ticketExport.cancel', locale)}</Button>
      <Button disabled={pending || !permitted || (!uncertain && (invalid.length > 0 || selected.length > 200 || config.count > 50000))} onClick={() => void submit()}>{t(pending ? 'ticketExport.creating' : uncertain ? 'ticketExport.confirmSubmission' : 'ticketExport.create', locale)}</Button>
    </div>
  </>
}
