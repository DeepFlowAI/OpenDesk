'use client'
/**
 * "Call prompt tones" settings section: four scene cards. Controlled by the
 * settings page so its Save button can submit transcription + prompt tones
 * together.
 */
import { useState } from 'react'
import { PromptToneCard } from './prompt-tone-card'
import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import { CALL_PROMPT_SCENES } from '@/models/call-prompt-tone'
import type { CallPromptTone } from '@/models/call-prompt-tone'

type Props = {
  locale: Locale
  scenes: CallPromptTone[]
  onChange: (next: CallPromptTone[]) => void
  disabled?: boolean
}

export function PromptToneSection({ locale, scenes, onChange, disabled }: Props) {
  const [activeToken, setActiveToken] = useState<string | null>(null)

  const byScene = new Map(scenes.map((s) => [s.scene, s]))
  const ordered = CALL_PROMPT_SCENES.map((s) => byScene.get(s)).filter(
    Boolean,
  ) as CallPromptTone[]

  const updateScene = (next: CallPromptTone) => {
    onChange(scenes.map((s) => (s.scene === next.scene ? next : s)))
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h2 className="text-sm font-medium text-foreground">
          {t('cpt.section.title', locale)}
        </h2>
        <p className="mt-1 max-w-[640px] text-sm leading-relaxed text-muted-foreground">
          {t('cpt.section.desc', locale)}
        </p>
      </div>
      <div className="flex flex-col gap-4">
        {ordered.map((s) => (
          <PromptToneCard
            key={s.scene}
            locale={locale}
            value={s}
            onChange={updateScene}
            disabled={disabled}
            activeToken={activeToken}
            onActivate={setActiveToken}
            onDeactivate={() => setActiveToken(null)}
          />
        ))}
      </div>
    </div>
  )
}
