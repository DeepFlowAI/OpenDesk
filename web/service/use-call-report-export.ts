import { useMutation } from '@tanstack/react-query'
import type { CallReportExportParams } from '@/models/call-report-export'
import { getBlob } from '@/service/base'

export async function downloadCallReportExport(params: CallReportExportParams) {
  const searchParams: Record<string, string> = { start: params.start, end: params.end }
  let endpoint: string

  switch (params.kind) {
    case 'overall':
      endpoint = 'v1/reports/calls/overall/export'
      searchParams.trend = params.trend
      break
    case 'queue-list':
      endpoint = 'v1/reports/calls/queues/export'
      searchParams.queue_type = params.queue_type
      searchParams.sort = params.sort
      searchParams.order = params.order
      if (params.q) searchParams.q = params.q
      break
    case 'queue-detail':
      endpoint = `v1/reports/calls/queues/${params.queue_type}/${params.queue_id}/export`
      searchParams.trend = params.trend
      break
    case 'employee-list':
      endpoint = 'v1/reports/calls/employees/export'
      searchParams.sort = params.sort
      searchParams.order = params.order
      if (params.q) searchParams.q = params.q
      if (params.group_id !== undefined) searchParams.group_id = String(params.group_id)
      if (params.status) searchParams.status = params.status
      break
    case 'employee-detail':
      endpoint = `v1/reports/calls/employees/${params.employee_id}/export`
      searchParams.trend = params.trend
      break
  }

  const { blob, headers } = await getBlob(endpoint, { searchParams })
  return { blob, filename: filenameFromContentDisposition(headers.get('content-disposition')) }
}

export const useCallReportExport = () => useMutation({ mutationFn: downloadCallReportExport })

export function filenameFromContentDisposition(value: string | null): string {
  if (!value) return 'call-report.xlsx'
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(value)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1])
    } catch {
      return encoded[1]
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(value)
  return quoted?.[1] || 'call-report.xlsx'
}
