import type { CallAgentSortField } from '@/models/call-agent-report'
import type { SortOrder, TrendType } from '@/models/call-report'
import type { CallQueueSortField, CallQueueType, CallQueueTypeFilter } from '@/models/call-queue-report'

type CommonParams = { start: string; end: string }

export type CallReportExportParams =
  | (CommonParams & { kind: 'overall'; trend: TrendType })
  | (CommonParams & { kind: 'queue-list'; q?: string; queue_type: CallQueueTypeFilter; sort: CallQueueSortField; order: SortOrder })
  | (CommonParams & { kind: 'queue-detail'; queue_type: CallQueueType; queue_id: number; trend: TrendType })
  | (CommonParams & { kind: 'employee-list'; q?: string; group_id?: number; status?: string; sort: CallAgentSortField; order: SortOrder })
  | (CommonParams & { kind: 'employee-detail'; employee_id: number; trend: TrendType })

export type CallEmployeeListExportState = {
  q?: string
  group_id?: number
  status?: string
  sort: CallAgentSortField
  order: SortOrder
}
