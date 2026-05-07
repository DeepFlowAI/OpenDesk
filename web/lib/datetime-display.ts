/**
 * Format API date/time strings (e.g. ISO 8601) for read-only display:
 * YYYY-MM-DD HH:mm:ss in the runtime local timezone, seconds precision (no sub-second).
 */
export function formatDatetimeForDisplay(raw: string): string {
  const d = new Date(raw.trim())
  if (Number.isNaN(d.getTime())) return raw
  const p2 = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ` +
    `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
  )
}
