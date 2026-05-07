'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { Switch } from '@/components/ui/switch'
import { useCreateVoiceFlow } from '@/service/use-voice-flows'

export default function NewVoiceFlowPage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const createMut = useCreateVoiceFlow()
  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)

  const snap = useMemo(() => JSON.stringify({ name: name.trim(), enabled }), [name, enabled])
  const isDirty = snap !== '{"name":"","enabled":true}'

  const handleSave = async () => {
    const n = name.trim()
    if (!n) return
    try {
      await createMut.mutateAsync({ name: n, enabled })
      router.push('/flow-studio/voice-flows')
    } catch {
      window.alert(t('vf.saveFailed', locale))
    }
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
          <span className="text-base font-semibold">{t('vf.form.newTitle', locale)}</span>
        </Link>
        <button
          type="button"
          disabled={!name.trim() || createMut.isPending || !isDirty}
          onClick={handleSave}
          className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-white disabled:opacity-40"
        >
          {createMut.isPending ? t('vf.form.saving', locale) : t('vf.form.save', locale)}
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
