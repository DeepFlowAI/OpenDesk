import type { OutboundTaskField } from '@/models/outbound-task'

export function autoOutboundTargetListFields(fields: OutboundTaskField[]): OutboundTaskField[] {
  return fields
    .filter((field) => field.enabled && field.show_in_list)
    .sort((a, b) => a.sort_order - b.sort_order)
}

export function autoOutboundTargetDetailFields(fields: OutboundTaskField[]): OutboundTaskField[] {
  return fields
    .filter((field) => field.enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
}
