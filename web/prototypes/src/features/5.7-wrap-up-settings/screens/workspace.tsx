import { IconCheck } from "@tabler/icons-react"
import { CallShell } from "@/prototypes/src/features/5.4-auto-outbound/components/call-shell"

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-b-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right text-sm font-medium">{value}</span>
    </div>
  )
}

function AuxCards({ duration }: { duration: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <div className="grid h-full min-h-[480px] gap-4 xl:grid-cols-3">
        <section className="rounded-xl border border-border bg-white p-5">
          <h3 className="text-sm font-semibold">通话信息</h3>
          <div className="mt-3 space-y-0.5 text-sm">
            <InfoRow label="通话类型" value="呼入" />
            <InfoRow label="用户号码" value="138 0013 8000" />
            <InfoRow label="服务号码" value="0755-8655 0123" />
            <InfoRow label="通话时长" value={duration} />
          </div>
        </section>
        <section className="rounded-xl border border-border bg-white p-5">
          <h3 className="text-sm font-semibold">用户信息</h3>
          <div className="mt-3 space-y-0.5 text-sm">
            <InfoRow label="姓名" value="王女士" />
            <InfoRow label="手机号" value="138 0013 8000" />
            <InfoRow label="所属组织" value="星海科技有限公司" />
          </div>
        </section>
        <section className="rounded-xl border border-border bg-white p-5">
          <h3 className="text-sm font-semibold">通话纪要</h3>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            客户确认本周完成续费评估，无需立即升级套餐。
          </p>
        </section>
      </div>
    </div>
  )
}

function WrapUpBar({ remaining }: { remaining: string }) {
  return (
    <div className="flex shrink-0 items-center gap-6 border-b border-border bg-background px-5 py-[18px]">
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
          <IconCheck size={16} className="text-amber-700" />
        </span>
        <div>
          <p className="font-bold">通话已结束，请整理本次记录</p>
          <p className="text-xs text-muted-foreground">本次通话时长：03:12</p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <span className="font-mono text-sm tabular-nums text-muted-foreground">
          整理剩余 {remaining}
        </span>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-full bg-green-500 text-white"
          title="完成整理"
        >
          <IconCheck size={16} />
        </button>
      </div>
    </div>
  )
}

export function WorkspaceWrapUpScreen() {
  return (
    <CallShell phase="wrap_up">
      <div className="flex h-full flex-col bg-muted/30">
        <WrapUpBar remaining="00:18" />
        <AuxCards duration="03:12" />
      </div>
    </CallShell>
  )
}

export function AutoOutboundAgentWrapUpScreen() {
  return (
    <CallShell phase="wrap_up">
      <div className="flex h-full flex-col bg-muted/30">
        <WrapUpBar remaining="00:42" />
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="mx-auto max-w-xl rounded-xl border border-border bg-white p-5">
            <div className="mb-4 flex items-center border-b border-border pb-2">
              <div className="flex rounded-md border border-border bg-muted p-0.5">
                <span className="rounded px-2 py-1 text-xs text-muted-foreground">通话纪要</span>
                <span className="rounded px-2 py-1 text-xs text-muted-foreground">新建工单</span>
                <span className="rounded bg-white px-2 py-1 text-xs font-medium shadow-sm">
                  外呼任务业务记录
                </span>
              </div>
            </div>
            <p className="rounded-lg bg-muted/50 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
              任务：到期续费提醒 · 超时结束整理中、坐席回到就绪
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">意向产品</div>
                <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">
                  企业版续费
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">外呼备注</div>
                <div className="min-h-[72px] rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
                  客户表示本周内部评估后回复，下周三上午再联系。
                </div>
              </div>
            </div>
            <button
              type="button"
              className="mt-5 h-10 w-full rounded-lg bg-primary text-sm font-medium text-primary-foreground"
            >
              提交业务记录并继续接单
            </button>
          </div>
        </div>
      </div>
    </CallShell>
  )
}
