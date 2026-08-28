import {
  CallStrip,
  CurrentExpandedBar,
  IdleDialRow,
  ProposedBar,
} from "../components/call-bar";
import { CompareCanvas } from "../components/shell";
import { ICON_LEGEND } from "../fixtures";

export function CallControlCompareScreen() {
  return (
    <CompareCanvas>
      <section className="overflow-hidden rounded-xl border border-border">
        <div className="bg-background px-4 py-2 text-xs font-semibold text-muted-foreground">
          空闲态 · 发起呼叫区（高度基准：px-5 py-5 + 内容 h-10）
        </div>
        <CallStrip tone="idle">
          <IdleDialRow />
        </CallStrip>
      </section>
      <section className="overflow-hidden rounded-xl border border-border">
        <div className="bg-background px-4 py-2 text-xs font-semibold text-muted-foreground">
          提案 · 通话中无输入框，只留「按键」入口发 DTMF
        </div>
        <CallStrip tone="active">
          <ProposedBar />
        </CallStrip>
      </section>
      <section className="space-y-2">
        <div className="text-xs font-semibold text-muted-foreground">现状 · 拨号区下再叠展开行，整体变高</div>
        <CurrentExpandedBar />
      </section>
      <section className="rounded-xl border border-border bg-background p-4">
        <div className="text-xs font-semibold text-muted-foreground">图标下方一词名称</div>
        <div className="mt-3 grid grid-cols-4 gap-3">
          {ICON_LEGEND.map((item) => (
            <div key={item.name}>
              <div className="text-sm font-medium">{item.name}</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </CompareCanvas>
  );
}
