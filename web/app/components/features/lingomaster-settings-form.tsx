'use client'

import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { IconLoader2 } from '@tabler/icons-react'

import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useLocaleStore } from '@/context/locale-store'
import { useLingoMasterSettings, useUpdateLingoMasterSettings } from '@/service/use-lingomaster'
import { t } from '@/utils/i18n'

const VARIABLES = [
  ['{{message}}', 'lingomaster.variable.message'],
  ['{{conversation_history}}', 'lingomaster.variable.history'],
  ['{{source_language}}', 'lingomaster.variable.source'],
  ['{{target_language}}', 'lingomaster.variable.target'],
] as const

function promptError(value: string, locale: Parameters<typeof t>[1]): string | null {
  if (!value.trim()) return t('lingomaster.validation.required', locale)
  if (value.length > 2000) return t('lingomaster.validation.maxLength', locale)
  if (!value.includes('{{message}}')) return t('lingomaster.validation.messageVariable', locale)
  return null
}

function PromptField({
  label,
  value,
  error,
  onChange,
  onReset,
}: {
  label: string
  value: string
  error: string | null
  onChange: (value: string) => void
  onReset: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <section className="space-y-3 border-t border-border pt-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <label className="text-sm font-semibold text-foreground">{label}</label>
          <p className="mt-1 text-sm text-muted-foreground">{t('lingomaster.prompt.hint', locale)}</p>
        </div>
        <button type="button" className="text-sm text-foreground underline-offset-4 hover:underline" onClick={onReset}>
          {t('lingomaster.restoreDefault', locale)}
        </button>
      </div>
      <Textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        className="min-h-48 resize-y bg-muted/40 font-mono text-[13px] leading-5"
      />
      <div className="flex min-h-5 items-center justify-between gap-4 text-xs">
        <span className={error ? 'text-destructive' : 'text-muted-foreground'}>
          {error ?? t('lingomaster.prompt.variablesReplaced', locale)}
        </span>
        <span className="text-muted-foreground">{value.length} / 2000</span>
      </div>
    </section>
  )
}

export function LingomasterSettingsForm() {
  const { locale } = useLocaleStore()
  const query = useLingoMasterSettings()
  const update = useUpdateLingoMasterSettings()
  const [enabled, setEnabled] = useState(false)
  const [visitorPrompt, setVisitorPrompt] = useState('')
  const [agentPrompt, setAgentPrompt] = useState('')
  const initial = useMemo(() => query.data ? JSON.stringify({
    enabled: query.data.enabled,
    visitor_prompt: query.data.visitor_prompt,
    agent_prompt: query.data.agent_prompt,
  }) : '', [query.data])
  const current = JSON.stringify({ enabled, visitor_prompt: visitorPrompt, agent_prompt: agentPrompt })
  const dirty = Boolean(initial && initial !== current)
  const visitorError = promptError(visitorPrompt, locale)
  const agentError = promptError(agentPrompt, locale)

  useEffect(() => {
    if (!query.data) return
    setEnabled(query.data.enabled)
    setVisitorPrompt(query.data.visitor_prompt)
    setAgentPrompt(query.data.agent_prompt)
  }, [query.data])

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [dirty])

  const save = async () => {
    if (visitorError || agentError) return
    try {
      await update.mutateAsync({ enabled, visitor_prompt: visitorPrompt, agent_prompt: agentPrompt })
      toast.success(t('lingomaster.saved', locale))
    } catch {
      toast.error(t('lingomaster.saveFailed', locale))
    }
  }

  if (query.isLoading) return <div className="h-96 animate-pulse rounded-lg bg-muted" />
  if (query.isError) return <div className="rounded-lg border border-destructive/30 p-6 text-sm text-destructive">{t('lingomaster.loadFailed', locale)}</div>

  return (
    <div className="mx-auto max-w-4xl pb-12">
      <div className="sticky top-0 z-10 -mx-1 flex items-center justify-between border-b border-border bg-background/90 px-1 py-3 backdrop-blur-sm">
        <div>
          <h1 className="font-display text-xl font-semibold text-foreground">{t('lingomaster.title', locale)}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('lingomaster.description', locale)}</p>
        </div>
        <Button disabled={!dirty || Boolean(visitorError || agentError) || update.isPending} onClick={() => void save()}>
          {update.isPending && <IconLoader2 className="animate-spin" />}
          {t('settings.save', locale)}
        </Button>
      </div>

      <section className="py-6">
        <div className="flex items-start justify-between gap-8 rounded-lg bg-muted/50 p-4">
          <div>
            <div className="text-sm font-medium text-foreground">{t('lingomaster.enable', locale)}</div>
            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{t('lingomaster.enableHint', locale)}</p>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} aria-label={t('lingomaster.enable', locale)} />
        </div>
      </section>

      <div className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-2 border-y border-border py-5 text-xs">
        {VARIABLES.map(([variable, key]) => (
          <div key={variable} className="contents">
            <code className="font-mono font-medium text-foreground">{variable}</code>
            <span className="text-muted-foreground">{t(key, locale)}</span>
          </div>
        ))}
      </div>

      <PromptField label={t('lingomaster.visitorPrompt', locale)} value={visitorPrompt} error={visitorError} onChange={setVisitorPrompt} onReset={() => setVisitorPrompt(query.data?.default_visitor_prompt ?? visitorPrompt)} />
      <PromptField label={t('lingomaster.agentPrompt', locale)} value={agentPrompt} error={agentError} onChange={setAgentPrompt} onReset={() => setAgentPrompt(query.data?.default_agent_prompt ?? agentPrompt)} />
    </div>
  )
}
