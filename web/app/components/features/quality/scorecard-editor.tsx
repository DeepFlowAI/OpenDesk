'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconPlus } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ScorecardCriterionEditor } from '@/app/components/features/quality/scorecard-criterion-editor'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import type { QualityScorecard, QualityScorecardCriterionInput, QualityScorecardPayload, QualityScorecardSectionInput } from '@/models/quality-scorecard'
import { useCreateQualityScorecardVersion, useDisableQualityScorecardVersion, usePublishQualityScorecard, useUpdateQualityScorecard } from '@/service/use-quality-scorecards'
import { hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'

type Props = { scorecard?: QualityScorecard; loading?: boolean }

function blankCriterion(locale: Locale): QualityScorecardCriterionInput {
  return {
    stable_key: crypto.randomUUID(), name: '', rubric: '', max_points: 10, is_required: true, evidence_policy: 'issue_only',
    options: [
      { name: t('ws.quality.scorecard.default.compliant', locale), description: '', points: 10, severity: 'normal' },
      { name: t('ws.quality.scorecard.default.partial', locale), description: '', points: 5, severity: 'notice' },
      { name: t('ws.quality.scorecard.default.noncompliant', locale), description: '', points: 0, severity: 'issue' },
    ],
  }
}

function initialForm(scorecard: QualityScorecard | undefined, locale: Locale): QualityScorecardPayload {
  if (!scorecard) return { name: '', description: '', pass_score: 80, sections: [{ name: t('ws.quality.scorecard.default.section', locale), criteria: [] }] }
  const version = scorecard.versions.find((item) => item.version_number === scorecard.current_version_number) ?? scorecard.versions.at(-1)
  return {
    name: scorecard.name, description: scorecard.description, pass_score: version?.pass_score ?? 80,
    sections: version?.sections.map((section) => ({ name: section.name, criteria: section.criteria.map((criterion) => ({ stable_key: criterion.stable_key, name: criterion.name, rubric: criterion.rubric, max_points: Number(criterion.max_points), is_required: criterion.is_required, evidence_policy: criterion.evidence_policy, options: criterion.options.map((option) => ({ name: option.name, description: option.description, points: Number(option.points), severity: option.severity })) })) })) ?? [],
  }
}

export function ScorecardEditor({ scorecard, loading = false }: Props) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const [form, setForm] = useState<QualityScorecardPayload>(() => initialForm(scorecard, locale))
  const [dirty, setDirty] = useState(false)
  const update = useUpdateQualityScorecard(); const publish = usePublishQualityScorecard(); const createVersion = useCreateQualityScorecardVersion(); const disableVersion = useDisableQualityScorecardVersion()
  const version = useMemo(() => scorecard?.versions.find((item) => item.version_number === scorecard.current_version_number) ?? scorecard?.versions.at(-1), [scorecard])
  const canManage = hasPermission(user, 'quality.online.scorecard.manage')
  const editable = canManage && version?.status === 'draft'
  const pending = update.isPending || publish.isPending || createVersion.isPending || disableVersion.isPending

  useEffect(() => { setForm(initialForm(scorecard, locale)); setDirty(false) }, [locale, scorecard])
  const change = (next: QualityScorecardPayload) => { setForm(next); setDirty(true) }
  const sections = form.sections ?? []
  const replaceSection = (index: number, next: QualityScorecardSectionInput) => change({ ...form, sections: sections.map((section, sectionIndex) => sectionIndex === index ? next : section) })

  const save = async () => {
    if (!scorecard || !form.name.trim()) return toast.error(t('ws.quality.scorecard.nameRequired', locale))
    try {
      await update.mutateAsync({ id: scorecard.id, payload: form })
      setDirty(false); toast.success(t('ws.quality.scorecard.saved', locale))
    } catch { toast.error(t('ws.quality.scorecard.saveFailed', locale)) }
  }
  const run = async (action: 'publish' | 'version' | 'disable') => {
    if (!scorecard || !version) return
    try {
      if (action === 'publish') await publish.mutateAsync(scorecard.id)
      if (action === 'version') await createVersion.mutateAsync(scorecard.id)
      if (action === 'disable') await disableVersion.mutateAsync({ id: scorecard.id, version: version.version_number })
      toast.success(t(`ws.quality.scorecard.${action === 'publish' ? 'published' : action === 'version' ? 'versionCreated' : 'disabled'}`, locale))
    } catch { toast.error(t('ws.quality.scorecard.actionFailed', locale)) }
  }

  if (loading) return <div className="p-8 text-sm text-muted-foreground">{t('common.loading', locale)}</div>
  if (!scorecard) return <div className="p-8 text-sm text-destructive">{t('common.loadFailed', locale)}</div>
  return <div className="h-full overflow-auto">
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background px-8">
      <button className="flex items-center gap-2 font-semibold" onClick={() => router.push('/workspace/quality/online/scorecards')}><IconArrowLeft size={20} />{scorecard.name}{version && <span className="text-sm font-normal text-muted-foreground">V{version.version_number} · {t(`ws.quality.status.${version.status}`, locale)}</span>}</button>
      <div className="flex gap-2">
        {editable && <Button variant="outline" disabled={!dirty || pending} onClick={() => void save()}>{t('ws.quality.scorecard.saveDraft', locale)}</Button>}
        {scorecard && version?.status === 'draft' && canManage && <Button disabled={pending || dirty} onClick={() => void run('publish')}>{t('ws.quality.scorecard.publish', locale)}</Button>}
        {scorecard && version?.status !== 'draft' && canManage && <Button variant="outline" disabled={pending} onClick={() => void run('version')}>{t('ws.quality.scorecard.newVersion', locale)}</Button>}
        {scorecard && version?.status === 'published' && canManage && <Button variant="destructive" disabled={pending} onClick={() => void run('disable')}>{t('ws.quality.scorecard.disable', locale)}</Button>}
      </div>
    </header>
    <main className="mx-auto max-w-5xl space-y-6 p-8">
      <section className="grid gap-4 rounded-lg border border-border bg-card p-5 md:grid-cols-2">
        <label className="space-y-1 text-sm"><span>{t('ws.quality.scorecard.name', locale)}</span><Input disabled={!editable} value={form.name} onChange={(event) => change({ ...form, name: event.target.value })} /></label>
        <label className="space-y-1 text-sm"><span>{t('ws.quality.scorecard.passScore', locale)}</span><Input disabled={!editable} type="number" min={0} max={100} step="0.1" value={form.pass_score ?? ''} onChange={(event) => change({ ...form, pass_score: event.target.value ? Number(event.target.value) : null })} /></label>
        <label className="space-y-1 text-sm md:col-span-2"><span>{t('ws.quality.scorecard.description', locale)}</span><Textarea disabled={!editable} value={form.description ?? ''} onChange={(event) => change({ ...form, description: event.target.value })} /></label>
      </section>
      {sections.map((section, sectionIndex) => <section key={`${sectionIndex}-${section.name}`} className="space-y-4 rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex gap-3"><Input disabled={!editable} value={section.name} onChange={(event) => replaceSection(sectionIndex, { ...section, name: event.target.value })} />{editable && <Button variant="outline" onClick={() => replaceSection(sectionIndex, { ...section, criteria: [...section.criteria, blankCriterion(locale)] })}><IconPlus />{t('ws.quality.scorecard.addCriterion', locale)}</Button>}{editable && sections.length > 1 && <Button variant="destructive" onClick={() => change({ ...form, sections: sections.filter((_, index) => index !== sectionIndex) })}>{t('ws.quality.scorecard.removeSection', locale)}</Button>}</div>
        {section.criteria.map((criterion, criterionIndex) => <ScorecardCriterionEditor key={criterion.stable_key ?? criterionIndex} criterion={criterion} disabled={!editable} onChange={(next) => replaceSection(sectionIndex, { ...section, criteria: section.criteria.map((item, index) => index === criterionIndex ? next : item) })} onRemove={() => replaceSection(sectionIndex, { ...section, criteria: section.criteria.filter((_, index) => index !== criterionIndex) })} />)}
      </section>)}
      {editable && <Button variant="outline" onClick={() => change({ ...form, sections: [...sections, { name: t('ws.quality.scorecard.newSection', locale), criteria: [] }] })}><IconPlus />{t('ws.quality.scorecard.addSection', locale)}</Button>}
    </main>
  </div>
}
