'use client'

import { IconX } from '@tabler/icons-react'
import type { SatisfactionFlowSettings } from '@/models/satisfaction-flow'

function Toggle({ label, description, checked, onChange }: {
  label: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-start justify-between gap-4 rounded-lg border border-border p-4">
      <span><span className="block text-sm font-medium">{label}</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">{description}</span></span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="mt-1" />
    </label>
  )
}

export function SatisfactionSettingsDrawer({ open, value, onClose, onApply }: {
  open: boolean
  value: SatisfactionFlowSettings
  onClose: () => void
  onApply: (value: SatisfactionFlowSettings) => void
}) {
  if (!open) return null
  const set = (patch: Partial<SatisfactionFlowSettings>) => onApply({ ...value, ...patch })
  const triggerInvalid = !value.auto_transfer && !value.agent_invite
  const directionInvalid = !value.inbound && !value.outbound
  return (
    <aside className="absolute inset-y-0 right-0 z-30 w-[430px] border-l border-border bg-card shadow-2xl">
      <header className="flex h-14 items-center justify-between border-b border-border px-5"><div><h2 className="text-sm font-semibold">应用设置</h2><p className="text-xs text-muted-foreground">决定何时把客户转入当前调查</p></div><button type="button" onClick={onClose} aria-label="关闭应用设置"><IconX size={18} /></button></header>
      <div className="space-y-6 overflow-y-auto p-5 pb-24">
        <section className="space-y-3"><h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">触发方式</h3><Toggle label="客服结束服务后自动转入" description="客服使用 OpenDesk 结束操作时，客户自动进入满意度。" checked={value.auto_transfer} onChange={(checked) => set({ auto_transfer: checked })} /><Toggle label="允许客服主动邀请" description="工作台显示邀请评价操作。" checked={value.agent_invite} onChange={(checked) => set({ agent_invite: checked })} />{triggerInvalid && <p className="text-xs text-destructive">请至少选择一种触发方式</p>}</section>
        <section className="space-y-3 border-t border-border pt-5"><h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">适用方向</h3><Toggle label="人工呼入" description="人工接通的呼入通话可触发。" checked={value.inbound} onChange={(checked) => set({ inbound: checked })} /><Toggle label="人工呼出" description="人工接通的呼出通话可触发。" checked={value.outbound} onChange={(checked) => set({ outbound: checked })} />{directionInvalid && <p className="text-xs text-destructive">请至少选择呼入或呼出</p>}</section>
      </div>
      <footer className="absolute inset-x-0 bottom-0 flex justify-end border-t border-border bg-card p-4"><button type="button" onClick={onClose} disabled={triggerInvalid || directionInvalid} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-40">应用</button></footer>
    </aside>
  )
}
