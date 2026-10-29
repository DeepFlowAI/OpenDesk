'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconArrowRight } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useLocaleStore } from '@/context/locale-store'
import type { QualityScorecardCreatePayload } from '@/models/quality-scorecard'
import { useCreateQualityScorecard } from '@/service/use-quality-scorecards'
import { t } from '@/utils/i18n'

const LIST_PATH = '/workspace/quality/online/scorecards'

export function buildQualityScorecardCreatePayload(name: string): QualityScorecardCreatePayload {
  return { name: name.trim() }
}

export function ScorecardCreateStep() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const create = useCreateQualityScorecard()
  const [name, setName] = useState('')

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const payload = buildQualityScorecardCreatePayload(name)
    if (!payload.name) {
      toast.error(t('ws.quality.scorecard.nameRequired', locale))
      return
    }
    try {
      const created = await create.mutateAsync(payload)
      router.replace(`${LIST_PATH}/${created.id}`)
    } catch {
      toast.error(t('ws.quality.scorecard.createFailed', locale))
    }
  }

  return (
    <div className="h-full overflow-auto">
      <header className="sticky top-0 z-20 flex h-14 items-center border-b border-border bg-background px-8">
        <button type="button" className="flex items-center gap-2 font-semibold" onClick={() => router.push(LIST_PATH)}>
          <IconArrowLeft size={20} />
          {t('ws.quality.scorecards.new', locale)}
        </button>
      </header>
      <main className="mx-auto max-w-xl p-8">
        <form className="space-y-6 rounded-xl border border-border bg-card p-6" onSubmit={(event) => void submit(event)}>
          <div>
            <h1 className="text-lg font-semibold">{t('ws.quality.scorecards.new', locale)}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t('ws.quality.scorecard.createHint', locale)}</p>
          </div>
          <label className="block space-y-2 text-sm">
            <span>{t('ws.quality.scorecard.name', locale)}</span>
            <Input autoFocus maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <div className="flex justify-end">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? t('ws.quality.scorecard.creating', locale) : t('ws.quality.scorecard.next', locale)}
              {!create.isPending && <IconArrowRight />}
            </Button>
          </div>
        </form>
      </main>
    </div>
  )
}
