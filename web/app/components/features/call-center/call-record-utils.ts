import type { CallRecordListItem, CallRecordingItem } from '@/models/call-center'

type CallRecordNumberFields = Pick<CallRecordListItem, 'customer_number' | 'service_number'>

export function callRecordCustomerNumber(record: CallRecordNumberFields): string | null {
  return record.customer_number
}

export function callRecordServiceNumber(record: CallRecordNumberFields): string | null {
  return record.service_number
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

const RECORDING_STATUS_RANK: Record<string, number> = {
  completed: 4,
  partial: 3,
  recording: 2,
  failed: 1,
}

function recordingPhaseRank(phase: string | null): number {
  if (phase === 'ai') return 2
  if (phase === 'bridged') return 1
  return 0
}

export function recordingPhaseLabel(phase: string | null, isZh: boolean): string | null {
  if (phase !== 'early_media') return null
  return isZh ? '线路提示录音' : 'Carrier announcement'
}

function compareDisplayRecordings(left: CallRecordingItem, right: CallRecordingItem): number {
  const playable = Number(Boolean(left.access_url)) - Number(Boolean(right.access_url))
  if (playable) return playable
  const status = (RECORDING_STATUS_RANK[left.status] ?? 0) - (RECORDING_STATUS_RANK[right.status] ?? 0)
  if (status) return status
  const duration = (left.duration_ms ?? -1) - (right.duration_ms ?? -1)
  if (duration) return duration
  const phase = recordingPhaseRank(left.phase) - recordingPhaseRank(right.phase)
  if (phase) return phase
  return (left.started_at ?? '').localeCompare(right.started_at ?? '')
}

export function selectDisplayRecording(
  recordings: CallRecordingItem[] | null | undefined,
): CallRecordingItem | null {
  if (!recordings?.length) return null
  return recordings.reduce((best, current) => (
    compareDisplayRecordings(current, best) > 0 ? current : best
  ))
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
