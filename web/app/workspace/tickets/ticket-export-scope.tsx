'use client'

import type { UnifiedField } from '@/models/field-definition'
import type { TicketExportConfig, TicketExportSource } from '@/models/ticket-export'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { t } from '@/utils/i18n'

export function TicketExportScope({ config, source }: { config: TicketExportConfig; source: TicketExportSource }) {
  const locale = source.language
  const unrestricted = t('ticketExport.unrestricted', locale)
  const query = config.prepared.query
  const fields = config.prepared.fields
  const groupField = fields.find((field) => field.slot_column != null && field.slot_column === query.group_field_col)
  const showValue = (field: UnifiedField, value: unknown) => <FieldValueDisplay fieldType={field.field_type} value={value} options={field.options} treeNodes={field.tree_nodes} typeConfig={field.type_config} />
  return <section className="space-y-2 text-sm">
    <p>{t('ticketExport.view', locale)}: {config.prepared.summary[locale]}</p>
    <p>{t('ticketExport.search', locale)}: {source.query.search || unrestricted}</p>
    {(['view_conditions', 'temp_conditions'] as const).map((key) => {
      const conditions = query[key] as { field_id?: number; field_key?: string; operator: string; value?: unknown }[] | undefined
      return <div key={key} className="space-y-1">
        <p>{t(key === 'view_conditions' ? 'ticketExport.viewFilters' : 'ticketExport.tempFilters', locale)} ({String(query[key.replace('conditions', 'condition_logic')] ?? 'and').toUpperCase()}): {!conditions?.length && unrestricted}</p>
        {conditions?.map((condition, index) => {
          const field = fields.find((item) => condition.field_id ? item.id === condition.field_id : item.key === condition.field_key)
          return <div key={index} className="flex flex-wrap items-center gap-1 pl-3">
            <span>{field?.name} {t(`ticketExport.operator.${condition.operator}`, locale)}</span>
            {field && condition.value != null && (Array.isArray(condition.value)
              ? condition.value.map((value, i) => <span key={i}>{i > 0 ? ', ' : ''}{showValue(field, value)}</span>)
              : showValue(field, condition.value))}
          </div>
        })}
      </div>
    })}
    <div className="flex gap-1">{t('ticketExport.group', locale)}: {source.query.group_value == null ? unrestricted : source.query.group_value === '__EMPTY__' ? t('ticketExport.emptyGroup', locale) : groupField ? showValue(groupField, source.query.group_value) : t('ticketExport.invalid', locale)}</div>
    <p>{t('ticketExport.sort', locale)}</p>
    <p>{t('ticketExport.count', locale, { count: config.count })}</p>
    <p className="text-muted-foreground">{t('ticketExport.dataNote', locale)}</p>
    <p>{t('ticketExport.format', locale)} · {locale === 'zh' ? '简体中文' : 'English'} · {source.timezone}</p>
    <p className="text-muted-foreground">{t('ticketExport.limits', locale)}</p>
    {config.count === 0 && <p>{t('ticketExport.zero', locale)}</p>}
  </section>
}
