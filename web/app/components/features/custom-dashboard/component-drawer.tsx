'use client'

import { useEffect, useMemo, useState } from 'react'
import CodeMirror, { type ReactCodeMirrorProps } from '@uiw/react-codemirror'
import { IconInfoCircle, IconPlayerPlay } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { DashboardResult } from './dashboard-result'
import type { DashboardComponent, DashboardRunResult } from '@/models/custom-dashboard'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { validateComponent } from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

const CODE_SETUP: ReactCodeMirrorProps['basicSetup'] = {
  lineNumbers: true,
  highlightActiveLineGutter: true,
  foldGutter: true,
  bracketMatching: true,
  closeBrackets: true,
  indentOnInput: true,
  highlightActiveLine: true,
  searchKeymap: true,
  tabSize: 4,
}

export function ComponentDrawer({
  component,
  open,
  running,
  onOpenChange,
  onApply,
  onPreview,
}: {
  component: DashboardComponent | null
  open: boolean
  running: boolean
  onOpenChange: (open: boolean) => void
  onApply: (component: DashboardComponent) => void
  onPreview: (component: DashboardComponent) => Promise<DashboardRunResult>
}) {
  const { locale } = useLocaleStore()
  const [draft, setDraft] = useState<DashboardComponent | null>(component)
  const [fieldKey, setFieldKey] = useState('system:status')
  const [preview, setPreview] = useState<DashboardRunResult | null>(null)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [tipVisible, setTipVisible] = useState(false)
  const fields = useUnifiedFields({ domain: 'ticket', locale, include_metadata: true })

  useEffect(() => {
    setDraft(component ? { ...component } : null)
    setPreview(null)
  }, [component])
  useEffect(() => {
    setTipVisible(localStorage.getItem('custom-dashboard-safety-tip-dismissed') !== '1')
  }, [])

  const availableFields = useMemo(() => (fields.data?.items ?? []).filter((field) => field.key && field.status === 'active'), [fields.data?.items])
  const dirty = Boolean(draft && component && (draft.title !== component.title || draft.code !== component.code))
  const error = draft ? validateComponent(draft) : null

  function requestClose() {
    if (dirty) setDiscardOpen(true)
    else onOpenChange(false)
  }

  async function runPreview() {
    if (!draft || error) return
    const response = await onPreview(draft)
    setPreview(response)
  }

  useEffect(() => {
    if (!open || !draft) return
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault()
        void runPreview()
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  })

  return (
    <>
      <Sheet open={open} onOpenChange={(next) => next ? onOpenChange(true) : requestClose()}>
        <SheetContent className="sm:max-w-2xl" showCloseButton={false}>
          <SheetHeader className="border-b border-border px-6 py-5">
            <SheetTitle>{t('cd.componentEditor', locale)}</SheetTitle>
            <SheetDescription>{t('cd.componentEditorHint', locale)}</SheetDescription>
          </SheetHeader>
          {draft && (
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
              {tipVisible && (
                <div className="flex gap-3 rounded-lg border border-border bg-muted/50 p-3 text-sm">
                  <IconInfoCircle className="mt-0.5 shrink-0 text-muted-foreground" size={18} />
                  <p className="flex-1 text-muted-foreground">{t('cd.safetyTip', locale)}</p>
                  <Button variant="ghost" size="xs" onClick={() => { localStorage.setItem('custom-dashboard-safety-tip-dismissed', '1'); setTipVisible(false) }}>{t('cd.dismiss', locale)}</Button>
                </div>
              )}
              <div className="grid gap-2">
                <Label htmlFor="component-title">{t('cd.componentTitle', locale)}</Label>
                <Input id="component-title" value={draft.title} maxLength={80} onChange={(event) => setDraft({ ...draft, title: event.target.value })} aria-invalid={error === 'title_required'} />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between"><Label>{t('cd.pythonCode', locale)}</Label><span className="text-xs text-muted-foreground">{new TextEncoder().encode(draft.code).length}/65536</span></div>
                <CodeMirror value={draft.code} onChange={(code) => setDraft({ ...draft, code })} height="320px" basicSetup={CODE_SETUP} indentWithTab className="overflow-hidden rounded-lg border border-border text-[13px] [&_.cm-scroller]:font-mono" />
                {error && <p className="text-xs text-destructive">{t(`cd.componentError.${error}`, locale)}</p>}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="component-field">{t('cd.insertField', locale)}</Label>
                <div className="flex gap-2">
                  <select id="component-field" value={fieldKey} onChange={(event) => setFieldKey(event.target.value)} className="h-8 min-w-0 flex-1 rounded-lg border border-border bg-background px-2 text-sm">
                    {availableFields.map((field) => <option key={field.key!} value={`${field.source}:${field.key}`}>{field.source === 'system' || field.source === 'metadata' ? `${field.source}:${field.key}` : `custom:${field.key}`} · {field.name}</option>)}
                  </select>
                  <Button type="button" variant="outline" onClick={() => setDraft({ ...draft, code: `${draft.code}${draft.code.endsWith('\n') ? '' : '\n'}"${fieldKey}"` })}>{t('cd.insert', locale)}</Button>
                </div>
              </div>
              <details className="rounded-lg border border-border p-4 text-sm">
                <summary className="cursor-pointer font-medium">{t('cd.runtimeCapabilities', locale)}</summary>
                <p className="mt-3 whitespace-pre-line text-muted-foreground">{t('cd.runtimeCapabilitiesBody', locale)}</p>
              </details>
              <div className="rounded-lg border border-border">
                <div className="flex items-center justify-between border-b border-border px-4 py-3"><span className="text-sm font-medium">{t('cd.runPreview', locale)}</span><Button variant="secondary" onClick={() => void runPreview()} disabled={running || !!error}><IconPlayerPlay />{running ? t('cd.preview.running', locale) : t('cd.run', locale)}</Button></div>
                <div className="min-h-40">
                  {preview?.status === 'success' && preview.result ? <DashboardResult output={preview.result} /> : preview ? <div className="space-y-2 p-4"><p className="text-sm text-destructive">{preview.message}</p>{preview.error_line && <p className="text-xs text-muted-foreground">{t('cd.errorLine', locale, { line: preview.error_line })}</p>}{preview.logs && <pre className="max-h-32 overflow-auto rounded bg-muted p-3 text-xs">{preview.logs}</pre>}</div> : <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">{t('cd.preview.empty', locale)}</div>}
                </div>
                {preview && <div className="border-t border-border px-4 py-2 text-xs text-muted-foreground">{t('cd.queryCount', locale, { count: preview.query_count })}{preview.logs_truncated ? ` · ${t('cd.logsTruncated', locale)}` : ''}</div>}
              </div>
            </div>
          )}
          <SheetFooter className="flex-row justify-end border-t border-border px-6 py-4">
            <Button variant="ghost" onClick={requestClose}>{t('cd.cancel', locale)}</Button>
            <Button disabled={!draft || !!error} onClick={() => { if (draft) { onApply(draft); onOpenChange(false) } }}>{t('cd.applyComponent', locale)}</Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
      <ConfirmDialog open={discardOpen} title={t('cd.discardTitle', locale)} message={t('cd.discardMessage', locale)} confirmLabel={t('cd.discard', locale)} onCancel={() => setDiscardOpen(false)} onConfirm={() => { setDiscardOpen(false); onOpenChange(false) }} />
    </>
  )
}
