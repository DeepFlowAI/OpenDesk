'use client'

import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useQualityReviewDetail } from '@/service/use-quality-reviews'
import { t } from '@/utils/i18n'

export function QualityReviewDetailView({ planId, reviewId }: { planId: number; reviewId: number }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading } = useQualityReviewDetail(reviewId)
  if (isLoading || !data) return <div className="p-8 text-sm text-muted-foreground">{t('common.loading', locale)}</div>
  return (
    <div className="h-full overflow-auto bg-muted/20">
      <header className="sticky top-0 z-10 flex h-14 items-center border-b bg-background px-6">
        <button className="flex items-center gap-2 font-semibold" onClick={() => router.push(`/workspace/quality/online/plans/${planId}`)}>
          <IconArrowLeft size={18} />{t('ws.quality.review.detail', locale)}
        </button>
      </header>
      <main className="mx-auto max-w-5xl space-y-5 p-6">
        <section className="grid gap-3 rounded-lg border bg-card p-5 sm:grid-cols-4">
          <Summary label={t('common.status', locale)} value={t(`ws.quality.review.status.${data.review.status}`, locale)} />
          <Summary label={t('ws.quality.review.source', locale)} value={data.review.result_source ? t(`ws.quality.review.source.${data.review.result_source}`, locale) : '--'} />
          <Summary label={t('ws.quality.review.score', locale)} value={data.review.score ?? '--'} />
          <Summary label={t('ws.quality.review.outcome', locale)} value={data.review.outcome ?? '--'} />
          {data.unable_reason && <p className="sm:col-span-4 text-sm text-muted-foreground">{data.unable_reason}</p>}
        </section>
        <section className="space-y-3">
          {data.items.map((item) => {
            const human = item.human
            const finalOption = item.criterion.options.find((option) => option.id === human.option_id)
            const aiOption = item.criterion.options.find((option) => option.id === item.ai.option_id)
            const showHuman = data.review.result_source === 'human'
            const showAi = item.ai.result_type != null
            return (
              <article key={item.review_item_id} className="rounded-lg border bg-card p-5">
                <h2 className="font-semibold">{item.criterion.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{item.criterion.rubric}</p>
                <div className={`mt-4 grid gap-4 ${showAi && showHuman ? 'md:grid-cols-2' : ''}`}>
                  {showAi && <div className="rounded-lg bg-blue-50 p-3 text-sm"><div className="text-xs font-medium text-blue-700">{t('ws.quality.review.aiOriginal', locale)}</div><div className="mt-1 font-medium">{aiOption?.name ?? item.ai.result_type}</div><p className="mt-1 text-muted-foreground">{item.ai.reason ?? '--'}</p></div>}
                  {showHuman && <div className="rounded-lg bg-muted p-3 text-sm"><div className="text-xs font-medium">{t('ws.quality.review.humanResult', locale)}</div><div className="mt-1 font-medium">{finalOption?.name ?? t(`ws.quality.review.${human.result_type === 'not_applicable' ? 'notApplicable' : 'unanswered'}`, locale)}</div><p className="mt-1 text-muted-foreground">{human.judgment || '--'}</p>{human.change_reason && <p className="mt-2 text-xs">{t('ws.quality.review.changeReason', locale)}：{human.change_reason}</p>}</div>}
                </div>
              </article>
            )
          })}
        </section>
        {data.audits.length > 0 && <section className="rounded-lg border bg-card p-5"><h2 className="font-semibold">{t('ws.quality.review.audit', locale)}</h2><div className="mt-3 space-y-2 text-sm">{data.audits.map((audit, index) => <div key={`${audit.created_at}-${index}`} className="flex justify-between border-t pt-2"><span>{audit.action} · #{audit.actor_id ?? '--'}</span><span className="text-muted-foreground">{new Date(audit.created_at).toLocaleString()}</span></div>)}</div></section>}
      </main>
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string | number }) {
  return <div><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 font-medium">{value}</div></div>
}
