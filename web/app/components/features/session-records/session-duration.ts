import type { SessionRecord } from '@/models/session-record'

function formatSecondsDuration(seconds: number): string {
  const diff = Math.max(0, Math.floor(seconds))
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  const s = diff % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function formatSessionDuration(record: Pick<SessionRecord, 'duration_seconds' | 'started_at' | 'ended_at'>): string {
  if (record.duration_seconds != null) {
    return formatSecondsDuration(record.duration_seconds)
  }
  if (!record.started_at) return '-'

  const start = new Date(record.started_at).getTime()
  const end = record.ended_at ? new Date(record.ended_at).getTime() : Date.now()
  return formatSecondsDuration((end - start) / 1000)
}
