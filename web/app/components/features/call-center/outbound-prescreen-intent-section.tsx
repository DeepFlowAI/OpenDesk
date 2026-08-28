'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconAlertTriangle, IconArrowLeft, IconPlus } from '@tabler/icons-react'
import { toast } from 'sonner'

import { OutboundPrescreenIntentDialog } from '@/app/components/features/call-center/outbound-prescreen-intent-dialog'
import { OutboundPrescreenIntentEditor } from '@/app/components/features/call-center/outbound-prescreen-intent-editor'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import type { OutboundPrescreenConfigDraft, OutboundPrescreenIntentDraft } from '@/models/outbound-prescreen'
import { useOutboundPrescreenConfig, useSaveOutboundPrescreenConfig } from '@/service/use-outbound-prescreen'
import { t } from '@/utils/i18n'

export function OutboundPrescreenIntentSection() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const query = useOutboundPrescreenConfig()
  const saveMutation = useSaveOutboundPrescreenConfig()
  const [draft, setDraft] = useState<OutboundPrescreenConfigDraft | null>(null)
  const [selected, setSelected] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)

  useEffect(() => {
    if (query.data) setDraft({ intents: query.data.intents.map(stripResponseFields) })
  }, [query.data])

  const persisted = useMemo(() => query.data ? JSON.stringify({ intents: query.data.intents.map(stripResponseFields) }) : '', [query.data])
  const dirty = draft !== null && JSON.stringify(draft) !== persisted

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const goBack = () => {
    if (
      dirty &&
      typeof window !== 'undefined' &&
      !window.confirm(t('prescreen.leaveConfirm', locale))
    ) {
      return
    }
    router.push('/call-center/settings')
  }

  const header = (saveDisabled: boolean, onSave?: () => void) => (
    <div className="sticky -top-8 z-20 flex min-h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6 py-2">
      <button type="button" onClick={goBack} className="flex min-w-0 items-center gap-2 text-left">
        <IconArrowLeft size={20} className="shrink-0 text-muted-foreground" />
        <span className="truncate text-base font-semibold text-foreground">
          {t('prescreen.title', locale)}
        </span>
      </button>
      <Button size="lg" disabled={saveDisabled} onClick={onSave}>
        {t(saveMutation.isPending ? 'prescreen.saving' : 'prescreen.save', locale)}
      </Button>
    </div>
  )

  if (query.isPending) {
    return (
      <div className="-m-8 flex flex-col">
        {header(true)}
        <div className="flex flex-col gap-4 p-8">
          <div className="h-5 w-96 max-w-full animate-pulse rounded bg-muted" />
          <div className="h-12 animate-pulse rounded-lg bg-muted" />
          <div className="h-72 animate-pulse rounded-xl bg-muted" />
        </div>
      </div>
    )
  }

  if (query.isError || !draft) {
    return (
      <div className="-m-8 flex flex-col">
        {header(true)}
        <div className="flex flex-col items-start gap-3 p-8">
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {t('prescreen.loadFailed', locale)}
          </p>
          <Button variant="outline" onClick={() => void query.refetch()}>
            {t('vc.retry', locale)}
          </Button>
        </div>
      </div>
    )
  }

  const active = draft.intents[selected] ?? draft.intents[0]
  const changeIntent = (index: number, value: OutboundPrescreenIntentDraft) => setDraft({ intents: draft.intents.map((item, itemIndex) => itemIndex === index ? value : item) })
  const save = async () => {
    try {
      const result = await saveMutation.mutateAsync(draft)
      setDraft({ intents: result.intents.map(stripResponseFields) })
      toast.success(t('prescreen.saved', locale))
    } catch { toast.error(t('prescreen.saveFailed', locale)) }
  }

  return (
    <div className="-m-8 flex flex-col">
      {header(!dirty || saveMutation.isPending, () => void save())}
      <div className="flex flex-col gap-4 p-8">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {t('prescreen.desc', locale)}
        </p>
        <div className="flex items-center gap-2 rounded-lg border border-info/20 bg-info/5 px-4 py-3 text-xs text-muted-foreground"><IconAlertTriangle size={16} className="shrink-0 text-info" />{t('prescreen.rule', locale)}</div>
        <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-4 py-3"><div><h3 className="text-sm font-semibold">{t('prescreen.list', locale)}</h3><p className="mt-1 text-xs text-muted-foreground">{t('prescreen.count', locale, { count: draft.intents.length })}</p></div><Button variant="outline" size="sm" disabled={draft.intents.length >= 20} onClick={() => setDialogOpen(true)}><IconPlus size={14} />{t('prescreen.new', locale)}</Button></div>
            <div className="divide-y divide-border">{draft.intents.map((intent, index) => <button key={intent.intent_key ?? `${intent.name}-${index}`} type="button" onClick={() => setSelected(index)} className={`w-full p-4 text-left transition-colors ${index === selected ? 'bg-muted/70' : 'hover:bg-muted/30'}`}><div className="flex items-center justify-between gap-2"><span className="text-sm font-semibold">{intent.name}</span><span className={`h-2 w-2 rounded-full ${intent.enabled ? 'bg-success' : 'bg-muted-foreground/40'}`} aria-label={t(intent.enabled ? 'prescreen.enabled' : 'prescreen.disabled', locale)} /></div><div className="mt-2 flex items-center justify-between text-xs text-muted-foreground"><span>{t('prescreen.expressionCount', locale, { count: intent.positive_examples.length })}</span><span className="font-mono">{t('prescreen.threshold', locale, { value: intent.similarity_threshold.toFixed(2) })}</span></div></button>)}</div>
          </div>
          {active && <OutboundPrescreenIntentEditor intent={active} config={draft} onChange={(value) => changeIntent(selected, value)} />}
        </div>
        <OutboundPrescreenIntentDialog open={dialogOpen} onOpenChange={setDialogOpen} onCreate={(intent) => { setDraft({ intents: [...draft.intents, intent] }); setSelected(draft.intents.length) }} />
      </div>
    </div>
  )
}

function stripResponseFields(intent: { id?: number; embeddings_ready?: boolean; created_at?: string; updated_at?: string } & OutboundPrescreenIntentDraft): OutboundPrescreenIntentDraft {
  return { intent_key: intent.intent_key, name: intent.name, enabled: intent.enabled, similarity_threshold: intent.similarity_threshold, is_system: intent.is_system, positive_examples: [...intent.positive_examples], negative_examples: [...intent.negative_examples] }
}
