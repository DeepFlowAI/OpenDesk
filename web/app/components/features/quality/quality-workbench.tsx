'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconCheck, IconDeviceFloppy, IconLink } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { useLocaleStore } from '@/context/locale-store'
import {
  useOpenQualityReview,
  useQualityWorkbench,
  useSaveQualityDraft,
  useSubmitQualityReview,
  useSubmitUnableQualityReview,
} from '@/service/use-quality-reviews'
import { t } from '@/utils/i18n'
import type { QualityDraftPayload, QualityHumanItem, QualityWorkbench } from '@/models/quality-review'

export function QualityWorkbenchView({ reviewId }: { reviewId: number }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const query = useQualityWorkbench(reviewId)
  const open = useOpenQualityReview()
  const save = useSaveQualityDraft()
  const submit = useSubmitQualityReview()
  const submitUnable = useSubmitUnableQualityReview()
  const opened = useRef(false)
  const [state, setState] = useState<QualityWorkbench | null>(null)
  const [activeId, setActiveId] = useState<number | null>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [unableOpen, setUnableOpen] = useState(false)
  const [unableReason, setUnableReason] = useState('')

  useEffect(() => {
    if (!query.data || opened.current) return
    opened.current = true
    if (query.data.review.status === 'pending_human') {
      void open.mutateAsync(reviewId).then(setState).catch(() => toast.error(t('common.loadFailed', locale)))
    } else {
      setState(query.data)
    }
  }, [locale, open, query.data, reviewId])

  useEffect(() => {
    if (state?.items.length && activeId == null) setActiveId(state.items[0].review_item_id)
  }, [activeId, state])

  const active = state?.items.find((item) => item.review_item_id === activeId)
  const payload = (): QualityDraftPayload => ({
    version: state?.draft_version ?? 0,
    overall_comment: state?.overall_comment,
    items: state?.items.map((item) => item.human) ?? [],
  })
  const updateHuman = (itemId: number, patch: Partial<QualityHumanItem>) => setState((current) => current ? ({ ...current, items: current.items.map((item) => item.review_item_id === itemId ? { ...item, human: { ...item.human, ...patch } } : item) }) : current)
  const toggleEvidence = (messageId: number, recalled: boolean) => {
    if (!active || recalled) return
    const exists = active.human.evidence_message_ids.includes(messageId)
    updateHuman(active.review_item_id, { evidence_message_ids: exists ? active.human.evidence_message_ids.filter((id) => id !== messageId) : [...active.human.evidence_message_ids, messageId] })
  }
  const saveDraft = async () => {
    try {
      const result = await save.mutateAsync({ reviewId, payload: payload() })
      setState(result)
      toast.success(t('ws.quality.review.saved', locale))
    } catch { toast.error(t('ws.quality.review.saveFailed', locale)) }
  }
  const submitReview = async () => {
    try {
      const result = await submit.mutateAsync({ reviewId, payload: payload() })
      setSubmitOpen(false)
      toast.success(t('ws.quality.review.submitted', locale))
      router.push(`/workspace/quality/online/plans/${result.review.plan_id}`)
    } catch { toast.error(t('ws.quality.review.validationFailed', locale)) }
  }
  const submitAsUnable = async () => {
    try {
      const result = await submitUnable.mutateAsync({ reviewId, payload: { ...payload(), reason: unableReason } })
      setUnableOpen(false)
      toast.success(t('ws.quality.review.submitted', locale))
      router.push(`/workspace/quality/online/plans/${result.review.plan_id}`)
    } catch { toast.error(t('ws.quality.review.validationFailed', locale)) }
  }
  const selectedEvidence = useMemo(() => new Set(active?.human.evidence_message_ids ?? []), [active])
  const aiEvidence = useMemo(() => new Set(active?.ai.evidence_message_ids ?? []), [active])
  if (!state) return <div className="p-8 text-sm text-muted-foreground">{t('common.loading', locale)}</div>

  return <div className="flex h-full min-h-0 flex-col bg-muted/20">
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-5"><button className="flex items-center gap-2 font-semibold" onClick={() => router.push(`/workspace/quality/online/plans/${state.review.plan_id}`)}><IconArrowLeft size={18} />{t('ws.quality.review.workbench', locale)}</button><div className="flex gap-2"><Button variant="outline" onClick={() => void saveDraft()} disabled={save.isPending}><IconDeviceFloppy size={16} />{t('ws.quality.review.save', locale)}</Button><Button variant="outline" onClick={() => setUnableOpen(true)}>{t('ws.quality.review.submitUnable', locale)}</Button><Button onClick={() => setSubmitOpen(true)}><IconCheck size={16} />{t('ws.quality.review.submit', locale)}</Button></div></header>
    <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(420px,.9fr)]">
      <section className="min-h-0 overflow-auto border-r p-5"><div className="mb-4"><h2 className="font-semibold">{(state.conversation_snapshot.agent_name as string | undefined) ?? `#${state.review.target_agent_id}`}</h2><p className="text-xs text-muted-foreground">{t('ws.quality.review.fullContext', locale)}</p></div><div className="space-y-3">{state.message_snapshot.map((message) => <button key={message.id} className={`block w-full rounded-lg border p-3 text-left ${selectedEvidence.has(message.id) ? 'border-primary bg-primary/5' : 'bg-card'} ${message.is_recalled ? 'opacity-60' : ''}`} onClick={() => toggleEvidence(message.id, message.is_recalled)}><div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground"><span>{message.sender_type}</span><span>{new Date(message.created_at).toLocaleString()}</span>{aiEvidence.has(message.id) && <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-700">AI</span>}{selectedEvidence.has(message.id) && <span className="rounded bg-primary/10 px-1.5 py-0.5 text-primary">{t('ws.quality.review.humanEvidence', locale)}</span>}{message.is_recalled && <span>{t('ws.quality.review.recalled', locale)}</span>}</div><p className="whitespace-pre-wrap text-sm">{message.content}</p></button>)}</div></section>
      <section className="min-h-0 overflow-auto bg-background p-5"><div className="space-y-3">{state.items.map((item) => { const changed = item.ai.result_type != null && (item.ai.result_type !== item.human.result_type || item.ai.option_id !== item.human.option_id); return <div key={item.review_item_id} className={`rounded-lg border ${activeId === item.review_item_id ? 'border-primary' : ''}`}><button className="flex w-full items-start justify-between p-4 text-left" onClick={() => setActiveId(item.review_item_id)}><div><div className="font-medium">{item.criterion.name}{item.criterion.is_required && <span className="ml-1 text-destructive">*</span>}</div><p className="mt-1 text-xs text-muted-foreground">{item.criterion.rubric}</p></div><IconLink size={16} className="mt-1 text-muted-foreground" /></button>{activeId === item.review_item_id && <div className="space-y-4 border-t p-4"><div className="rounded-lg bg-blue-50 p-3 text-sm"><div className="text-xs font-medium text-blue-700">{t('ws.quality.review.aiOriginal', locale)}</div><p className="mt-1">{item.ai.reason ?? '--'}</p></div><label className="block space-y-1 text-sm"><span>{t('ws.quality.review.humanResult', locale)}</span><select className="h-9 w-full rounded-lg border bg-background px-2" value={item.human.result_type === 'option' ? `option:${item.human.option_id}` : item.human.result_type} onChange={(event) => { const [kind, raw] = event.target.value.split(':'); updateHuman(item.review_item_id, { result_type: kind as QualityHumanItem['result_type'], option_id: kind === 'option' ? Number(raw) : null }) }}><option value="unanswered">{t('ws.quality.review.unanswered', locale)}</option><option value="not_applicable">{t('ws.quality.review.notApplicable', locale)}</option>{item.criterion.options.map((option) => <option key={option.id} value={`option:${option.id}`}>{option.name} · {option.points}</option>)}</select></label><label className="block space-y-1 text-sm"><span>{t('ws.quality.review.judgment', locale)}</span><Textarea value={item.human.judgment ?? ''} onChange={(event) => updateHuman(item.review_item_id, { judgment: event.target.value })} /></label>{changed && <label className="block space-y-1 text-sm"><span>{t('ws.quality.review.changeReason', locale)} *</span><Textarea value={item.human.change_reason ?? ''} onChange={(event) => updateHuman(item.review_item_id, { change_reason: event.target.value })} /></label>}<p className="text-xs text-muted-foreground">{t('ws.quality.review.evidenceHint', locale, { count: item.human.evidence_message_ids.length })}</p></div>}</div>})}</div><label className="mt-5 block space-y-1 text-sm"><span>{t('ws.quality.review.overallComment', locale)}</span><Textarea className="min-h-24" value={state.overall_comment ?? ''} onChange={(event) => setState({ ...state, overall_comment: event.target.value })} /></label></section>
    </div>
    <Dialog open={submitOpen} onOpenChange={setSubmitOpen}><DialogContent><DialogHeader><DialogTitle>{t('ws.quality.review.submitTitle', locale)}</DialogTitle></DialogHeader><p className="text-sm text-muted-foreground">{t('ws.quality.review.submitMessage', locale)}</p><DialogFooter><Button variant="outline" onClick={() => setSubmitOpen(false)}>{t('ws.quality.cancel', locale)}</Button><Button onClick={() => void submitReview()} disabled={submit.isPending}>{t('ws.quality.review.confirmSubmit', locale)}</Button></DialogFooter></DialogContent></Dialog>
    <Dialog open={unableOpen} onOpenChange={setUnableOpen}><DialogContent><DialogHeader><DialogTitle>{t('ws.quality.review.unableTitle', locale)}</DialogTitle></DialogHeader><p className="text-sm text-muted-foreground">{t('ws.quality.review.unableMessage', locale)}</p><Textarea value={unableReason} onChange={(event) => setUnableReason(event.target.value)} placeholder={t('ws.quality.review.unablePlaceholder', locale)} /><DialogFooter><Button variant="outline" onClick={() => setUnableOpen(false)}>{t('ws.quality.cancel', locale)}</Button><Button disabled={unableReason.trim().length < 10 || submitUnable.isPending} onClick={() => void submitAsUnable()}>{t('ws.quality.review.confirmSubmit', locale)}</Button></DialogFooter></DialogContent></Dialog>
  </div>
}
