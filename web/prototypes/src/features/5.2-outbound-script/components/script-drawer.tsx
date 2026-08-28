import {
  IconArrowLeft,
  IconCheck,
  IconGitBranch,
  IconListTree,
  IconRefresh,
  IconX,
} from "@tabler/icons-react";
import { SCRIPT_DIRECTORY } from "../fixtures";

const DEPTH_PADDING = ["pl-2", "pl-[22px]", "pl-9", "pl-[50px]", "pl-16"];

export function GuidedScriptDrawer({ preview = false }: { preview?: boolean }) {
  return (
    <aside className="flex h-full w-[520px] shrink-0 flex-col border-l border-border bg-background">
      <div className="flex h-[66px] shrink-0 items-center justify-between border-b border-border px-5">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-base font-semibold">{preview ? "预览话术流程" : "话术流程"}</h2>
            {preview && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">预览</span>}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">客户满意度回访 · 第 2 步</p>
        </div>
        <div className="flex items-center gap-1">
          <button className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground"><IconListTree size={15} />查看全部</button>
          <button className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground"><IconRefresh size={15} /></button>
          <button className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground"><IconX size={16} /></button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mb-5 flex items-center gap-3">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">2</span>
          <h3 className="font-display text-base font-semibold">确认沟通意愿</h3>
        </div>
        <div className="mt-5 rounded-xl border border-border bg-card p-5">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">建议话术</div>
          <p className="mt-3 text-[17px] leading-7 text-foreground">“想占用您两三分钟，对我们最近一次服务做个简单回访。请问您现在方便吗？”</p>
        </div>
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
          <div className="text-xs font-semibold">客服提示</div>
          <p className="mt-1.5 text-sm leading-6">如果客户正在开会或开车，不要继续追问，优先约定方便的回拨时间。</p>
        </div>
        <div className="mt-6">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><IconGitBranch size={16} />客户反馈</div>
          <div className="grid grid-cols-3 gap-2.5">
            {[
              ["方便沟通", "进入服务评价"],
              ["现在不方便", "约定回拨时间"],
              ["明确拒绝", "礼貌结束沟通"],
            ].map(([label, next], index) => (
              <button key={label} className={`flex min-h-20 min-w-0 flex-col items-start justify-center rounded-lg border px-3 text-left text-sm ${index === 0 ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background"}`}>
                <span className="font-medium">{label}</span><span className={`mt-1 text-xs leading-4 ${index === 0 ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{next}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="flex h-16 shrink-0 items-center justify-between border-t border-border px-5">
        <button className="inline-flex items-center gap-2 text-sm text-muted-foreground"><IconArrowLeft size={16} />上一步</button>
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><IconCheck size={14} />选择客户的实际反馈</span>
      </div>
    </aside>
  );
}

export function AllScriptsDrawer() {
  return (
    <aside className="flex h-full w-[620px] shrink-0 flex-col border-l border-border bg-background">
      <div className="flex h-[66px] shrink-0 items-center justify-between border-b border-border px-5">
        <div><h2 className="font-display text-base font-semibold">全部话术</h2><p className="mt-0.5 text-xs text-muted-foreground">客户满意度回访 · 12 个步骤</p></div>
        <div className="flex items-center gap-1"><button className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground"><IconGitBranch size={15} />逐步引导</button><button className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground"><IconX size={16} /></button></div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="max-h-[42%] shrink-0 overflow-y-auto border-b border-border bg-muted/30 p-3">
          {SCRIPT_DIRECTORY.map((item) => (
            <div key={`${item.depth}-${item.label}`} className={`mb-0.5 flex h-8 items-center rounded-md pr-2 text-xs ${DEPTH_PADDING[item.depth]} ${item.active ? "bg-background font-semibold shadow-sm" : "text-muted-foreground"}`}>
              <span className="mr-1.5 text-[10px]">{item.depth > 0 ? "└" : "●"}</span><span className="truncate">{item.label}</span>
            </div>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          <div className="flex items-center gap-3">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">2</span>
            <h3 className="font-display text-base font-semibold">确认沟通意愿</h3>
          </div>
          <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">建议话术</div>
          <p className="mt-3 text-base leading-7">“想占用您两三分钟，对我们最近一次服务做个简单回访。请问您现在方便吗？”</p>
          <div className="mt-5 rounded-lg bg-amber-50 p-4 text-sm leading-6 text-amber-950">客户不方便时不要继续追问，优先约定回拨时间。</div>
          <div className="mt-6 border-t border-border pt-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><IconGitBranch size={16} />客户反馈</div>
            <div className="grid grid-cols-3 gap-2">
              {[
                ["方便沟通", "进入服务评价"],
                ["现在不方便", "约定回拨时间"],
                ["明确拒绝", "礼貌结束沟通"],
              ].map(([label, next], index) => (
                <button key={label} className={`flex min-h-20 min-w-0 flex-col items-start justify-center rounded-lg border px-2.5 text-left ${index === 0 ? "border-primary bg-primary text-primary-foreground" : "border-border bg-background"}`}>
                  <span className="whitespace-nowrap text-sm font-medium">{label}</span><span className={`mt-1 whitespace-nowrap text-[11px] leading-4 ${index === 0 ? "text-primary-foreground/70" : "text-muted-foreground"}`}>{next}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
