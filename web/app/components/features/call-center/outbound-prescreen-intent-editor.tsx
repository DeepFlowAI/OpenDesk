'use client'

import { useState } from 'react'
import { IconFlask, IconPlayerPlay, IconTargetArrow } from '@tabler/icons-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { type Locale, useLocaleStore } from '@/context/locale-store'
import type {
  OutboundPrescreenConfigDraft,
  OutboundPrescreenDecision,
  OutboundPrescreenIntentDraft,
} from '@/models/outbound-prescreen'
import { useTestOutboundPrescreen } from '@/service/use-outbound-prescreen'
import { t } from '@/utils/i18n'

type Props = {
  intent: OutboundPrescreenIntentDraft
  config: OutboundPrescreenConfigDraft
  onChange: (intent: OutboundPrescreenIntentDraft) => void
}

const lines = (value: string) => value.split('\n').map((item) => item.trim()).filter(Boolean)

export function OutboundPrescreenIntentEditor({ intent, config, onChange }: Props) {
  const { locale } = useLocaleStore()
  const tester = useTestOutboundPrescreen()
  const [testText, setTestText] = useState('')
  const [decision, setDecision] = useState<OutboundPrescreenDecision | null>(null)
  const update = <K extends keyof OutboundPrescreenIntentDraft>(key: K, value: OutboundPrescreenIntentDraft[K]) => onChange({ ...intent, [key]: value })

  const runTest = async () => {
    try {
      const result = await tester.mutateAsync({ config, text: testText, voiced_ms: 800, voice_match: true })
      setDecision(result)
    } catch {
      toast.error(t('prescreen.testFailed', locale))
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div><h3 className="text-sm font-semibold">{intent.name}</h3><p className="mt-1 text-xs text-muted-foreground">{t('prescreen.editHint', locale)}</p></div>
        <div className="flex items-center gap-2 text-xs"><span>{t(intent.enabled ? 'prescreen.enabled' : 'prescreen.disabled', locale)}</span><Switch checked={intent.enabled} disabled={!intent.enabled && intent.positive_examples.length < 5} onCheckedChange={(value) => update('enabled', value)} aria-label={t('prescreen.title', locale)} /></div>
      </div>
      <div className="grid gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <ExampleField label={t('prescreen.positives', locale)} hint={t('prescreen.positivesHint', locale)} values={intent.positive_examples} onChange={(value) => update('positive_examples', value)} />
          <ExampleField label={t('prescreen.negatives', locale)} hint={t('prescreen.negativesHint', locale)} values={intent.negative_examples} onChange={(value) => update('negative_examples', value)} />
        </div>
        <div className="space-y-4">
          <div className="rounded-lg border border-border p-4">
            <div className="flex items-center gap-2 text-xs font-semibold"><IconTargetArrow size={16} />{t('prescreen.thresholdTitle', locale)}</div>
            <div className="mt-3 flex items-center gap-2"><Input className="w-28 font-mono text-base font-semibold" type="number" min={0.5} max={0.99} step={0.01} value={intent.similarity_threshold} onChange={(event) => update('similarity_threshold', Number(event.target.value))} /><span className="text-xs text-muted-foreground">0.50–0.99</span></div>
            <p className="mt-2 text-xs text-muted-foreground">{t('prescreen.thresholdHint', locale)}</p>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <div className="flex items-center gap-2 text-xs font-semibold"><IconFlask size={16} />{t('prescreen.testTitle', locale)}</div>
            <div className="mt-3 flex gap-2"><Input value={testText} onChange={(event) => setTestText(event.target.value)} placeholder={t('prescreen.testPlaceholder', locale)} /><Button variant="outline" disabled={!testText.trim() || tester.isPending} onClick={() => void runTest()}><IconPlayerPlay size={15} />{t(tester.isPending ? 'prescreen.testing' : 'prescreen.test', locale)}</Button></div>
            {decision && <DecisionResult decision={decision} locale={locale} />}
          </div>
        </div>
      </div>
    </section>
  )
}

function ExampleField({ label, hint, values, onChange }: { label: string; hint: string; values: string[]; onChange: (values: string[]) => void }) {
  return <label className="block"><span className="flex items-center justify-between text-xs font-semibold"><span>{label}</span><span className="font-normal text-muted-foreground">{values.length} / 200</span></span><span className="mt-1 block text-xs font-normal text-muted-foreground">{hint}</span><Textarea className="mt-2 min-h-32 leading-7" value={values.join('\n')} onChange={(event) => onChange(lines(event.target.value))} /></label>
}

function DecisionResult({ decision, locale }: { decision: OutboundPrescreenDecision; locale: Locale }) {
  return <div className={`mt-3 rounded-md border px-3 py-2.5 ${decision.auto_hangup ? 'border-success/25 bg-success/5' : 'border-warning/25 bg-warning/5'}`}><div className="flex items-center justify-between gap-3"><span className="text-xs font-semibold">{decision.auto_hangup ? t('prescreen.matched', locale, { name: decision.intent_name ?? '-' }) : t('prescreen.uncertain', locale)}</span>{decision.similarity !== null && <span className="font-mono text-sm">{decision.similarity.toFixed(2)} / {decision.threshold?.toFixed(2)}</span>}</div><p className="mt-1 text-xs text-muted-foreground">{decision.matched_positive ? t('prescreen.similar', locale, { text: decision.matched_positive }) : t('prescreen.reason', locale, { reason: decision.reason ?? '-' })}</p></div>
}
