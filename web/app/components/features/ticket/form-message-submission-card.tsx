'use client'

import { IconForms } from '@tabler/icons-react'

import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'
import type { TicketFormSubmission } from '@/models/ticket'
import type { FieldType } from '@/types/field-enums'

const SOURCE_LABELS: Record<string, { zh: string; en: string }> = {
  outside_service_hours: { zh: '服务时间外', en: 'Outside service hours' },
  queue_waiting: { zh: '排队中留言', en: 'While waiting in queue' },
  queue_full: { zh: '队列超限', en: 'Queue full' },
  bot_handoff: { zh: '机器人转人工', en: 'Bot handoff' },
  bot_action: { zh: '机器人操作', en: 'Bot action' },
}

export function FormMessageSubmissionCard({
  submission,
  isZh,
}: {
  submission: TicketFormSubmission
  isZh: boolean
}) {
  const fields = [...submission.field_snapshot].sort((a, b) => a.sort_order - b.sort_order)
  const source = SOURCE_LABELS[submission.source]

  return (
    <section className="rounded-lg border border-border bg-background p-4" aria-labelledby="form-message-submission-title">
      <div className="flex items-center gap-2">
        <IconForms size={18} className="text-muted-foreground" />
        <h3 id="form-message-submission-title" className="text-sm font-semibold text-foreground">
          {isZh ? '表单留言信息' : 'Form message information'}
        </h3>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <Metadata label={isZh ? '来源渠道' : 'Source channel'} value={submission.channel_name} />
        <Metadata label={isZh ? '提交时间' : 'Submitted at'} value={formatDatetimeForDisplay(submission.submitted_at)} />
        <Metadata label={isZh ? '来源场景' : 'Source'} value={source ? (isZh ? source.zh : source.en) : submission.source} />
        {submission.conversation_public_id && (
          <Metadata label={isZh ? '来源会话' : 'Source conversation'} value={submission.conversation_public_id} />
        )}
      </dl>

      <div className="mt-5 border-t border-border pt-4">
        <h4 className="text-xs font-medium text-muted-foreground">
          {isZh ? '工单字段提交快照' : 'Ticket field submission snapshot'}
        </h4>
        <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
          {fields.map((field) => (
            <div key={`${field.field_key ?? field.field_id}-${field.sort_order}`} className="min-w-0">
              <dt className="mb-1 text-xs text-muted-foreground">{field.name}</dt>
              <dd className="min-w-0 text-sm text-foreground">
                <FieldValueDisplay
                  fieldType={field.field_type as FieldType}
                  value={field.value}
                  typeConfig={field.type_config}
                  options={field.options}
                  treeNodes={field.tree_nodes}
                />
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words text-foreground">{value || '—'}</dd>
    </div>
  )
}
