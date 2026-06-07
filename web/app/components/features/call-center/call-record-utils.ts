import type { CallRecordListItem } from '@/models/call-center'

type CallRecordNumberFields = Pick<CallRecordListItem, 'direction' | 'from_number' | 'to_number'>

export function callRecordCustomerNumber(record: CallRecordNumberFields): string | null {
  return record.direction === 'outbound' ? record.to_number : record.from_number
}

export function callRecordServiceNumber(record: CallRecordNumberFields): string | null {
  return record.direction === 'outbound' ? record.from_number : record.to_number
}

export function formatCallRecordDuration(ms: number | null): string {
  if (ms == null) return '-'
  const seconds = Math.floor(ms / 1000)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = seconds % 60
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
}

export function formatQueueDurationSeconds(seconds: number | null): string {
  if (seconds == null || seconds < 0) return ''
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = seconds % 60
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
}

export function formatCallRecordDate(value: string | null, isZh = true): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(isZh ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}
