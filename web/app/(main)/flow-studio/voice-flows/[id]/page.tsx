'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Switch } from '@/components/ui/switch'
import { useVoiceFlow, useUpdateVoiceFlow } from '@/service/use-voice-flows'

export default function EditVoiceFlowPage() {
  const params = useParams()
  const { locale } = useLocaleStore()
  const raw = params.id as string
  const id = Number.parseInt(raw, 10)
  const { data: flow, isLoading } = useVoiceFlow(Number.isNaN(id) ? 0 : id)
  const updateMut = useUpdateVoiceFlow()

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (flow && !ready) {
      setName(flow.name)
      setEnabled(flow.enabled)
      setReady(true)
    }
  }, [flow, ready])

  const savedSnap = useMemo(() => {
    if (!flow) return ''
    return JSON.stringify({ name: flow.name.trim(), enabled: flow.enabled })
  }, [flow])

  const currentSnap = useMemo(
    () => JSON.stringify({ name: name.trim(), enabled }),
    [name, enabled]
  )

  const isDirty = ready && currentSnap !== savedSnap

  const handleSave = async () => {
    const n = name.trim()
    if (!n || Number.isNaN(id)) return
    try {
      await updateMut.mutateAsync({ id, data: { name: n, enabled } })
    } catch {
      window.alert(t('vf.saveFailed', locale))
    }
  }

  if (Number.isNaN(id)) {
    return <p className="text-sm text-red-600">Invalid id</p>
  }

  if (isLoading || !flow) {
    return <p className="text-sm text-muted-foreground">{t('vf.loading', locale)}</p>
  }

  return (
    <div className="flex flex-col">
      <div className="sticky top-0 z-20 -mx-8 mb-6 flex items-center justify-between border-b border-border bg-white px-8 py-4">
        <Link
          href="/flow-studio/voice-flows"
          onClick={(e) => {
            if (
              isDirty &&
              typeof window !== 'undefined' &&
              !window.confirm(t('rr.form.leaveConfirm', locale))
            )
              e.preventDefault()
          }}
          className="flex items-center gap-2 text-foreground hover:text-foreground/80"
        >
          <IconArrowLeft size={20} />
          <span className="text-base font-semibold">
            {t('vf.form.editTitle', locale, { name: flow.name })}
          </span>
        </Link>
        <button
          type="button"
          disabled={!name.trim() || updateMut.isPending || !isDirty}
          onClick={handleSave}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white disabled:opacity-40"
        >
          {updateMut.isPending ? t('vf.form.saving', locale) : t('vf.form.save', locale)}
        </button>
      </div>

      <div className="max-w-lg space-y-6">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground/80">
            {t('vf.form.name', locale)}
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('vf.form.name.placeholder', locale)}
            className="h-10 w-full rounded-lg border border-border px-3 text-sm"
          />
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground/80">{t('vf.form.enabled', locale)}</span>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>
      </div>
    </div>
  )
}
