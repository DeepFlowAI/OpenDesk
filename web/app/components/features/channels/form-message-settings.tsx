'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconArrowDown, IconArrowUp, IconGripVertical, IconPlus, IconSearch, IconTrash } from '@tabler/icons-react'

import { Switch } from '@/components/ui/switch'
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useLocaleStore } from '@/context/locale-store'
import type { ChannelFormMessageConfig } from '@/models/channel'
import type { UnifiedField } from '@/models/field-definition'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { FIELD_TYPE_LABELS } from '@/types/field-enums'
import { t } from '@/utils/i18n'
import {
  configuredFormFieldUid,
  formFieldUid,
  isPublicFormField,
  toConfiguredFormField,
  validateFormMessageConfig,
} from '@/lib/form-message-fields'

type Props = {
  mode: 'conversation' | 'form'
  config: ChannelFormMessageConfig
  error: string
  onModeChange: (mode: 'conversation' | 'form') => void
  onChange: (config: ChannelFormMessageConfig) => void
  onValidationChange: (error: string) => void
}

const inputClass = 'h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring'

export function FormMessageSettings({
  mode,
  config,
  error,
  onModeChange,
  onChange,
  onValidationChange,
}: Props) {
  const { locale } = useLocaleStore()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pendingFieldUids, setPendingFieldUids] = useState<Set<string>>(new Set())
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const { data, isLoading } = useUnifiedFields({ domain: 'ticket', locale, include_metadata: false })
  const allFields = useMemo(() => data?.items ?? [], [data?.items])
  const byUid = useMemo(() => new Map(allFields.map((field) => [formFieldUid(field), field])), [allFields])
  const selectedUids = useMemo(
    () => new Set(config.fields.map(configuredFormFieldUid)),
    [config.fields],
  )
  const available = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    return allFields.filter((field) => (
      isPublicFormField(field)
      && !selectedUids.has(formFieldUid(field))
      && (!needle || field.name.toLocaleLowerCase().includes(needle))
    ))
  }, [allFields, search, selectedUids])

  useEffect(() => {
    if (mode !== 'form') {
      onValidationChange('')
      return
    }
    const invalidConfiguredField = config.fields.some((field) => {
      const definition = byUid.get(configuredFormFieldUid(field))
      return data && (!definition || !isPublicFormField(definition))
    })
    const validationKey = invalidConfiguredField ? 'fields_unavailable' : validateFormMessageConfig(config)
    onValidationChange(validationKey ? t(`ch.form.formMessage.error.${validationKey}`, locale) : '')
  }, [byUid, config, data, locale, mode, onValidationChange])

  const update = <K extends keyof ChannelFormMessageConfig>(key: K, value: ChannelFormMessageConfig[K]) => {
    onChange({ ...config, [key]: value })
  }

  const move = (index: number, offset: -1 | 1) => {
    const target = index + offset
    if (target < 0 || target >= config.fields.length) return
    const fields = [...config.fields]
    ;[fields[index], fields[target]] = [fields[target], fields[index]]
    update('fields', fields)
  }

  const addPendingFields = () => {
    const added = allFields
      .filter((field) => pendingFieldUids.has(formFieldUid(field)))
      .map(toConfiguredFormField)
    update('fields', [...config.fields, ...added])
    setPendingFieldUids(new Set())
    setPickerOpen(false)
  }

  const dropAt = (targetIndex: number) => {
    if (draggedIndex == null || draggedIndex === targetIndex) return
    const fields = [...config.fields]
    const [dragged] = fields.splice(draggedIndex, 1)
    fields.splice(targetIndex, 0, dragged)
    update('fields', fields)
    setDraggedIndex(null)
  }

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium text-foreground">{t('ch.form.formMessage.mode', locale)}</p>
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-muted p-1">
          {(['conversation', 'form'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => onModeChange(value)}
              className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${mode === value ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {t(`ch.form.formMessage.mode.${value}`, locale)}
            </button>
          ))}
        </div>
        <p className="text-xs leading-5 text-muted-foreground">{t('ch.form.formMessage.mode.hint', locale)}</p>
      </div>

      {mode === 'form' && (
        <div className="mt-5 flex flex-col gap-5 border-t border-border pt-5">
          <TextField label={t('ch.form.formMessage.title', locale)} value={config.title} maxLength={64} onChange={(value) => update('title', value)} />
          <TextAreaField label={t('ch.form.formMessage.description', locale)} value={config.description} maxLength={1000} onChange={(value) => update('description', value)} />

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-foreground">{t('ch.form.formMessage.fields', locale)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('ch.form.formMessage.fields.hint', locale)}</p>
              </div>
              <button type="button" onClick={() => { setPendingFieldUids(new Set()); setPickerOpen(true) }} className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs font-medium text-foreground hover:bg-accent">
                <IconPlus size={15} />{t('ch.form.formMessage.addField', locale)}
              </button>
            </div>

            <Sheet open={pickerOpen} onOpenChange={setPickerOpen}>
              <SheetContent side="right" className="w-full sm:max-w-md">
                <SheetHeader className="border-b border-border">
                  <SheetTitle>{t('ch.form.formMessage.addField', locale)}</SheetTitle>
                </SheetHeader>
                <div className="min-h-0 flex-1 overflow-y-auto px-4">
                  <div className="relative mb-3">
                    <IconSearch size={15} className="absolute left-3 top-3 text-muted-foreground" />
                    <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('ch.form.formMessage.searchFields', locale)} className={`${inputClass} pl-9 focus:ring-inset`} />
                  </div>
                  <div className="space-y-1">
                    {isLoading ? (
                      <p className="px-2 py-4 text-center text-xs text-muted-foreground">{t('common.loading', locale)}</p>
                    ) : available.length === 0 ? (
                      <p className="px-2 py-4 text-center text-xs text-muted-foreground">{t('ch.form.formMessage.noFields', locale)}</p>
                    ) : available.map((field) => {
                      const uid = formFieldUid(field)
                      const selected = pendingFieldUids.has(uid)
                      return (
                        <button key={uid} type="button" onClick={() => setPendingFieldUids((current) => { const next = new Set(current); if (selected) next.delete(uid); else next.add(uid); return next })} className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left ${selected ? 'border-primary bg-primary/5' : 'border-transparent hover:bg-accent'}`}>
                          <span className="text-sm text-foreground">{field.name}</span>
                          <span className="text-xs text-muted-foreground">{FIELD_TYPE_LABELS[field.field_type]?.[locale === 'zh' ? 'zh' : 'en'] ?? field.field_type}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
                <SheetFooter className="grid grid-cols-2 border-t border-border">
                  <button type="button" onClick={() => setPickerOpen(false)} className="h-10 rounded-md border border-border text-sm font-medium text-foreground">{locale === 'zh' ? '取消' : 'Cancel'}</button>
                  <button type="button" disabled={pendingFieldUids.size === 0} onClick={addPendingFields} className="h-10 rounded-md bg-primary text-sm font-medium text-primary-foreground disabled:opacity-50">{locale === 'zh' ? '添加' : 'Add'}</button>
                </SheetFooter>
              </SheetContent>
            </Sheet>

            {config.fields.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">{t('ch.form.formMessage.emptyFields', locale)}</div>
            ) : config.fields.map((field, index) => {
              const definition = byUid.get(configuredFormFieldUid(field))
              const unavailable = Boolean(data && (!definition || !isPublicFormField(definition)))
              return (
                <div
                  key={configuredFormFieldUid(field)}
                  draggable
                  onDragStart={() => setDraggedIndex(index)}
                  onDragEnd={() => setDraggedIndex(null)}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={() => dropAt(index)}
                  className={`flex items-center gap-3 rounded-lg border p-3 ${unavailable ? 'border-destructive/60' : 'border-border'} ${draggedIndex === index ? 'opacity-50' : ''}`}
                >
                  <IconGripVertical size={17} className="shrink-0 cursor-grab text-muted-foreground" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{definition?.name ?? configuredFormFieldUid(field)}</p>
                    <p className={`mt-0.5 text-xs ${unavailable ? 'text-destructive' : 'text-muted-foreground'}`}>
                      {unavailable ? t('ch.form.formMessage.unavailableField', locale) : definition?.source === 'system' ? t('ch.form.formMessage.systemField', locale) : t('ch.form.formMessage.customField', locale)}
                    </p>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    {t('ch.form.formMessage.required', locale)}
                    <Switch checked={field.required} onCheckedChange={(required) => update('fields', config.fields.map((item, itemIndex) => itemIndex === index ? { ...item, required } : item))} />
                  </label>
                  <button type="button" disabled={index === 0} aria-label={t('common.moveUp', locale)} onClick={() => move(index, -1)} className="text-muted-foreground disabled:opacity-30"><IconArrowUp size={16} /></button>
                  <button type="button" disabled={index === config.fields.length - 1} aria-label={t('common.moveDown', locale)} onClick={() => move(index, 1)} className="text-muted-foreground disabled:opacity-30"><IconArrowDown size={16} /></button>
                  <button type="button" aria-label={t('common.remove', locale)} onClick={() => update('fields', config.fields.filter((_, itemIndex) => itemIndex !== index))} className="text-muted-foreground hover:text-destructive"><IconTrash size={16} /></button>
                </div>
              )
            })}
          </div>

          <p className="rounded-lg bg-muted px-3 py-2 text-xs leading-5 text-muted-foreground">{t('ch.form.formMessage.userHint', locale)}</p>
          <TextField label={t('ch.form.formMessage.submitLabel', locale)} value={config.submit_label} maxLength={16} onChange={(value) => update('submit_label', value)} />
          <TextField label={t('ch.form.formMessage.successTitle', locale)} value={config.success_title} maxLength={64} onChange={(value) => update('success_title', value)} />
          <TextAreaField label={t('ch.form.formMessage.successDescription', locale)} value={config.success_description} maxLength={1000} onChange={(value) => update('success_description', value)} />
          <label className="flex items-center justify-between gap-4 text-sm font-medium text-foreground">
            {t('ch.form.formMessage.showTicketNumber', locale)}
            <Switch checked={config.show_ticket_number} onCheckedChange={(value) => update('show_ticket_number', value)} />
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )}
    </div>
  )
}

function TextField({ label, value, maxLength, onChange }: { label: string; value: string; maxLength: number; onChange: (value: string) => void }) {
  return <label className="flex flex-col gap-2"><span className="text-sm font-medium text-foreground">{label}<span className="text-destructive"> *</span></span><input value={value} maxLength={maxLength} onChange={(event) => onChange(event.target.value)} className={inputClass} /></label>
}

function TextAreaField({ label, value, maxLength, onChange }: { label: string; value: string; maxLength: number; onChange: (value: string) => void }) {
  return <label className="flex flex-col gap-2"><span className="text-sm font-medium text-foreground">{label}</span><textarea value={value} maxLength={maxLength} onChange={(event) => onChange(event.target.value)} className="min-h-24 w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring" /></label>
}
