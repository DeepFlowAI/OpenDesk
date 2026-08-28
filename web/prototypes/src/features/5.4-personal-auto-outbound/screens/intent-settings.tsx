import {
  IconAlertTriangle,
  IconCheck,
  IconFlask,
  IconPlus,
  IconPlayerPlay,
  IconSettings,
  IconTargetArrow,
  IconX,
} from "@tabler/icons-react";
import { AdminShell } from "@/prototypes/src/features/5.5-embedded-pages/components/admin-shell";

const INTENTS = [
  { name: "明确拒绝", samples: 6, threshold: "0.86", selected: true, enabled: true },
  { name: "暂不方便", samples: 5, threshold: "0.88", selected: false, enabled: false },
  { name: "禁止再次联系", samples: 5, threshold: "0.92", selected: false, enabled: false },
];

const POSITIVE_SAMPLES = ["不需要", "没有兴趣", "不用了，谢谢", "我不考虑", "不想了解", "暂时不需要"];
const NEGATIVE_SAMPLES = ["不是不需要，我是现在没空", "你先说是什么事", "我没说不需要"];

function SampleEditor({ items, placeholder }: { items: string[]; placeholder: string }) {
  return (
    <textarea
      defaultValue={items.join("\n")}
      placeholder={placeholder}
      rows={items.length}
      className="mt-2 w-full resize-none rounded-lg border border-border bg-background px-3 py-2.5 text-xs leading-7 outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/40"
    />
  );
}

export function PersonalOutboundIntentSettingsScreen() {
  return (
    <AdminShell active="call-settings">
      <div className="flex h-full flex-col overflow-hidden bg-surface">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-border bg-background px-6">
          <div>
            <div className="flex items-center gap-2"><IconSettings size={19} /><h1 className="font-display text-xl font-bold">外呼预筛意图</h1></div>
            <p className="mt-1 text-xs text-muted-foreground">通过语义相似度识别客户的口头拒绝；客户主动挂机由线路事件直接处理</p>
          </div>
          <button className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground">保存配置</button>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden p-6">
          <div className="flex h-full flex-col gap-4">
            <div className="flex shrink-0 items-center gap-2 rounded-lg border border-info/20 bg-info/5 px-4 py-3 text-xs text-muted-foreground">
              <IconAlertTriangle size={16} className="shrink-0 text-info" />
              所有启用的预筛意图命中后，均播放当前客服的礼貌结束语并自动挂机；这里不配置其他处理动作。
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-[330px_minmax(0,1fr)] gap-4">
              <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
                <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3.5"><div><h2 className="text-sm font-semibold">预筛意图</h2><p className="mt-1 text-[11px] text-muted-foreground">选择意图后维护识别表达和阈值</p></div><button className="inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs font-medium transition-colors hover:bg-muted"><IconPlus size={14} />新建意图</button></div>
                <div className="min-h-0 flex-1 divide-y divide-border overflow-y-auto">
                  {INTENTS.map((intent) => (
                    <div key={intent.name} className={`p-4 transition-colors ${intent.selected ? "bg-muted/70" : "bg-background"}`}>
                      <div className="flex items-center justify-between"><span className="text-sm font-semibold">{intent.name}</span><span className={`h-4 w-7 rounded-full p-0.5 ${intent.enabled ? "bg-primary" : "bg-muted-foreground/30"}`}><span className={`block h-3 w-3 rounded-full bg-background ${intent.enabled ? "ml-3" : ""}`} /></span></div>
                      <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground"><span>{intent.samples} 条相似表达</span><span>阈值 {intent.threshold}</span></div>
                      {intent.selected && <div className="mt-3 flex items-center gap-1 text-[11px] font-medium"><IconCheck size={13} />正在编辑</div>}
                    </div>
                  ))}
                </div>
                <div className="border-t border-border px-4 py-3 text-[11px] text-muted-foreground">共 3 个意图，最多可创建 20 个</div>
              </section>

              <section className="min-h-0 overflow-y-auto rounded-xl border border-border bg-card">
                <div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">明确拒绝</h2><p className="mt-1 text-[11px] text-muted-foreground">每行填写一条表达，保存后用于后续外呼预筛</p></div>
                <div className="grid grid-cols-[minmax(0,1fr)_360px] gap-5 p-5">
                  <div className="space-y-5">
                    <div>
                      <div className="flex items-center justify-between"><span className="text-xs font-semibold">相似表达</span><span className="text-[11px] text-muted-foreground">6 / 200</span></div>
                      <p className="mt-1 text-[11px] text-muted-foreground">一行一个，至少维护 5 条代表性客户说法</p>
                      <SampleEditor items={POSITIVE_SAMPLES} placeholder={"例如：\n不需要\n没有兴趣"} />
                    </div>
                    <div>
                      <div className="flex items-center justify-between"><span className="text-xs font-semibold">易混淆反例</span><span className="text-[11px] text-muted-foreground">3 / 200</span></div>
                      <p className="mt-1 text-[11px] text-muted-foreground">一行一个，用于排除包含拒绝词但不应挂机的表达</p>
                      <SampleEditor items={NEGATIVE_SAMPLES} placeholder={"例如：\n不是不需要，我是现在没空"} />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="rounded-lg border border-border p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold"><IconTargetArrow size={15} />相似度阈值</div>
                      <div className="mt-3 flex items-center gap-2"><input type="number" min="0.5" max="0.99" step="0.01" defaultValue="0.86" className="h-10 w-28 rounded-md border border-border bg-background px-3 font-mono text-lg font-semibold outline-none focus:border-foreground/40" /><span className="text-[11px] text-muted-foreground">范围 0.50–0.99</span></div>
                      <p className="mt-3 text-[11px] leading-4 text-muted-foreground">阈值越高越保守；低于阈值时转人工。</p>
                    </div>
                    <div className="rounded-lg border border-border bg-muted/30 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold"><IconFlask size={15} />单句测试</div>
                      <div className="mt-3 flex gap-2"><input defaultValue="我真的不需要，谢谢" className="h-9 min-w-0 flex-1 rounded-md border border-border bg-background px-3 text-xs outline-none focus:border-foreground/40" /><button className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-xs font-medium"><IconPlayerPlay size={14} />测试识别</button></div>
                      <div className="mt-3 rounded-md border border-success/25 bg-success/5 px-3 py-2.5"><div className="flex items-center justify-between gap-3"><div className="text-xs font-semibold text-success">命中：明确拒绝</div><div className="shrink-0 font-mono text-sm font-semibold">0.93 <span className="text-[10px] font-normal text-muted-foreground">/ 0.86</span></div></div><div className="mt-0.5 text-[11px] text-muted-foreground">最相似表达“不需要” · 达到阈值后自动挂机</div></div>
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </div>
        </main>
      </div>
    </AdminShell>
  );
}

export function PersonalOutboundNewIntentScreen() {
  return (
    <div className="relative h-full">
      <PersonalOutboundIntentSettingsScreen />
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-foreground/25 p-6 backdrop-blur-[1px]">
        <div className="w-[460px] rounded-xl border border-border bg-background shadow-2xl">
          <div className="flex items-start justify-between border-b border-border px-5 py-4"><div><h2 className="text-base font-semibold">新建预筛意图</h2><p className="mt-1 text-xs text-muted-foreground">创建后继续维护相似表达和易混淆反例</p></div><button className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"><IconX size={17} /></button></div>
          <div className="space-y-5 p-5">
            <div><label className="text-xs font-semibold">意图名称</label><input placeholder="例如：价格不合适" className="mt-2 h-10 w-full rounded-md border border-border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus:border-foreground/40" /><p className="mt-1.5 text-[11px] text-muted-foreground">2–20 个字符，租户内不可重名</p></div>
            <div><label className="text-xs font-semibold">相似度阈值</label><div className="mt-2 flex items-center gap-2"><input type="number" min="0.5" max="0.99" step="0.01" defaultValue="0.86" className="h-10 w-28 rounded-md border border-border bg-background px-3 font-mono text-sm outline-none focus:border-foreground/40" /><span className="text-[11px] text-muted-foreground">范围 0.50–0.99</span></div></div>
            <div className="rounded-lg border border-info/20 bg-info/5 p-3 text-[11px] leading-4 text-muted-foreground">新意图默认停用。创建后至少添加 5 条相似表达并保存，才可以启用参与预筛。</div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-4"><button className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium">取消</button><button className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"><IconPlus size={15} />创建意图</button></div>
        </div>
      </div>
    </div>
  );
}
