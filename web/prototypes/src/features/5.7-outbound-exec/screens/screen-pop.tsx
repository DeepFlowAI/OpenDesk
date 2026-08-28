import { IconArrowLeft, IconPlus } from "@tabler/icons-react";
import { OnCallBar, OutboundExecShell } from "../components/shell";

const TRANSCRIPT = [
  { role: "客服", text: "您好，我是 XX 团队的客服小张，请问是张伟先生吗？" },
  { role: "客户", text: "是我，你说什么事？" },
  { role: "客服", text: "您上周咨询过续费的事情，这次想跟您确认一下意向。" },
];

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

export function OutboundExecScreenPopScreen() {
  return (
    <OutboundExecShell callBar={<OnCallBar />}>
      <div className="flex min-h-0 flex-1 flex-col bg-muted/40 p-5">
        <div className="mb-4">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-primary shadow-sm">
            <IconArrowLeft size={13} />
            返回外呼任务
          </span>
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-3 gap-4">
          <section className="flex min-h-0 flex-col rounded-xl border border-border bg-card p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">通话信息</h3>
            <div className="divide-y divide-border/60">
              <InfoRow label="通话类型" value="呼出" />
              <InfoRow label="外呼号码" value="0755-8655 0123" />
              <InfoRow label="被叫号码" value="138****8888" />
              <InfoRow label="通话时长" value="02:41" />
              <InfoRow label="发起时间" value="2026-08-17 14:30" />
            </div>
            <h4 className="mb-2 mt-4 text-xs font-semibold text-muted-foreground">实时字幕</h4>
            <div className="flex-1 space-y-2 overflow-hidden">
              {TRANSCRIPT.map((line, index) => (
                <div key={index} className="rounded-lg bg-muted/60 px-3 py-2 text-xs">
                  <span className="font-medium text-primary">{line.role}：</span>
                  {line.text}
                </div>
              ))}
            </div>
          </section>

          <section className="flex min-h-0 flex-col rounded-xl border border-border bg-card p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">客户信息</h3>
            <div className="flex items-center gap-3 rounded-lg bg-muted/60 p-3">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                张
              </span>
              <div>
                <div className="text-sm font-semibold">张伟</div>
                <div className="font-mono text-xs text-muted-foreground">138****8888</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="rounded-md bg-info/10 px-2 py-0.5 text-[11px] font-medium text-info">普通客户</span>
              <span className="rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">深圳</span>
            </div>
            <h4 className="mb-2 mt-4 text-xs font-semibold text-muted-foreground">最近工单</h4>
            <div className="space-y-2">
              <div className="rounded-lg border border-border p-2.5 text-xs">
                <div className="font-medium">续费咨询</div>
                <div className="mt-0.5 text-muted-foreground">处理中 · 2026-08-15</div>
              </div>
              <div className="rounded-lg border border-border p-2.5 text-xs">
                <div className="font-medium">发票信息修改</div>
                <div className="mt-0.5 text-muted-foreground">已解决 · 2026-07-28</div>
              </div>
            </div>
          </section>

          <section className="flex min-h-0 flex-col rounded-xl border border-border bg-card p-4 shadow-sm">
            <div className="mb-3 flex rounded-md border border-border bg-muted p-0.5">
              <span className="flex-1 rounded bg-background px-2 py-1 text-center text-xs font-medium shadow-sm">
                通话纪要
              </span>
              <span className="flex-1 px-2 py-1 text-center text-xs text-muted-foreground">新建工单</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">纪要内容</div>
                <div className="h-28 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
                  记录本次通话要点…
                </div>
              </div>
              <span className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm">
                <IconPlus size={15} />
                保存纪要
              </span>
            </div>
          </section>
        </div>
      </div>
    </OutboundExecShell>
  );
}
