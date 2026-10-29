'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import type { UnifiedField } from '@/models/field-definition'
import { exportFieldUid } from '@/models/ticket-export'
import { t } from '@/utils/i18n'

export function TicketExportFields({ fields, selected, defaults, onChange, language, disabled }: {
  fields: UnifiedField[]; selected: string[]; defaults: string[]
  onChange: (fields: string[]) => void; language: 'zh' | 'en'; disabled: boolean
}) {
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState(false)
  const change = (next: string[]) => {
    setLimit(next.length > 200)
    if (next.length <= 200) onChange(next)
  }
  return <section className="space-y-3">
    <div className="flex items-center justify-between"><h3 className="font-medium">{t('ticketExport.fields', language)}</h3><span>{selected.length} / 200</span></div>
    <Input aria-label={t('ticketExport.searchFields', language)} placeholder={t('ticketExport.searchFields', language)} value={search} maxLength={100} onChange={(event) => setSearch(event.target.value)} />
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={disabled} onClick={() => change(defaults)}>{t('ticketExport.restore', language)}</Button>
      <Button variant="ghost" disabled={disabled} onClick={() => change(fields.map(exportFieldUid))}>{t('ticketExport.all', language)}</Button>
      <Button variant="ghost" disabled={disabled} onClick={() => change(['key:ticket_number'])}>{t('ticketExport.clear', language)}</Button>
    </div>
    {limit && <p role="alert" className="text-destructive">{t('exports.error.column_limit', language)}</p>}
    {[false, true].map((custom) => <fieldset key={String(custom)} disabled={disabled} className="space-y-3">
      <legend className="mb-2 text-muted-foreground">{t(custom ? 'ticketExport.custom' : 'ticketExport.system', language)}</legend>
      <div className="grid grid-cols-2 gap-3">{fields.filter((field) => (field.source === 'custom') === custom && field.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map((field) => {
        const uid = exportFieldUid(field)
        return <label key={uid} className="flex items-center gap-2"><Checkbox checked={selected.includes(uid)} disabled={disabled || uid === 'key:ticket_number'} onCheckedChange={(checked) => change(checked ? [...selected, uid] : selected.filter((value) => value !== uid))} />{field.name}</label>
      })}</div>
    </fieldset>)}
    {!fields.some((field) => field.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())) && <p className="text-muted-foreground">{t('ticketExport.noFields', language)}</p>}
  </section>
}
