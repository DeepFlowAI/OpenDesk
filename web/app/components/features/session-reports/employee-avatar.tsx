import type { EmployeeBrief } from '@/models/session-report'

const AVATAR_PALETTE = ['#3B82F6', '#8B5CF6', '#10B981', '#F59E0B', '#6366F1', '#EC4899', '#EF4444']

function pickColor(id: number) {
  return AVATAR_PALETTE[id % AVATAR_PALETTE.length]
}

function firstChar(name: string | null | undefined, fallback: string): string {
  const s = (name ?? '').trim()
  return s ? s.charAt(0) : fallback
}

type Props = {
  employee: EmployeeBrief
  size?: number
}

export function EmployeeAvatar({ employee, size = 32 }: Props) {
  if (employee.avatar) {
    return (
      <img
        src={employee.avatar}
        alt={employee.display_name ?? employee.name}
        width={size}
        height={size}
        className="shrink-0 rounded-full object-cover"
      />
    )
  }
  const ch = firstChar(employee.display_name, firstChar(employee.name, '?'))
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full text-xs font-semibold text-background"
      style={{ width: size, height: size, backgroundColor: pickColor(employee.id) }}
      aria-hidden
    >
      {ch}
    </div>
  )
}
