import { IconCheck, IconChevronDown, IconFileMusic, IconInfoCircle, IconMicrophone, IconPlayerPlay, IconPlayerStop, IconSparkles, IconUsers, IconX } from "@tabler/icons-react";
import { PersonalOutboundWorkspaceShell } from "../components/workspace-shell";
import { SessionHeader } from "../components/session-ui";

function SelectField({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <label className="block">
      <span className="text-xs font-medium">{label}</span>
      <div className="mt-1.5 flex h-10 items-center justify-between rounded-md border border-border bg-background px-3 text-sm"><span>{value}</span><IconChevronDown size={15} className="text-muted-foreground" /></div>
      {note && <span className="mt-1 block text-[11px] text-muted-foreground">{note}</span>}
    </label>
  );
}

function RecordingRow({ label, file, duration, updatedAt }: { label: string; file: string; duration: string; updatedAt: string }) {
  return (
    <div>
      <div className="text-xs font-medium">{label}</div>
      <div className="mt-1.5 flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2.5">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-primary text-primary-foreground"><IconFileMusic size={18} /></div>
        <div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{file}</div><div className="mt-0.5 text-[11px] text-muted-foreground">{duration} · WAV · {updatedAt}</div></div>
        <div className="flex h-7 items-end gap-0.5 px-1">{["h-2", "h-3.5", "h-5", "h-3", "h-6", "h-4", "h-2.5", "h-[18px]", "h-3.5", "h-2"].map((heightClass, index) => <span key={index} className={`w-0.5 rounded-full bg-foreground/35 ${heightClass}`} />)}</div>
        <button className="grid h-8 w-8 place-items-center rounded-full border border-border bg-background"><IconPlayerPlay size={15} /></button>
        <button className="inline-flex h-8 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-xs font-medium"><IconMicrophone size={14} />录制</button>
        <button className="h-8 rounded-md border border-border bg-background px-2.5 text-xs font-medium">上传</button>
      </div>
    </div>
  );
}

export function PersonalOutboundConfigScreen() {
  return (
    <PersonalOutboundWorkspaceShell>
      <div className="flex h-full flex-col">
        <SessionHeader status="未开始" actions={<button className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"><IconSparkles size={16} />开始自动外呼</button>} />
        <div className="min-h-0 flex-1 overflow-hidden p-6">
          <div className="grid h-full grid-cols-[minmax(0,1.45fr)_minmax(310px,0.8fr)] gap-5">
            <section className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">外呼配置</h2><p className="mt-1 text-xs text-muted-foreground">两段录音和主客服均为张琪，运行后配置将锁定</p></div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-5 p-5">
                <SelectField label="来源任务" value="到期续费提醒" note="我的可呼叫对象 86 人" />
                <SelectField label="主叫号码" value="0755-8655 0123" note="企业客服热线 · 当前可用" />
                <div className="col-span-2 space-y-3">
                  <RecordingRow label="本人开场录音" file="张琪｜续费提醒开场白.wav" duration="00:08" updatedAt="今天 09:32 更新" />
                  <label className="block">
                    <span className="text-xs font-medium">开场白文案</span>
                    <span className="ml-1.5 text-[11px] text-muted-foreground">选填 · 转人工后展示给你自己看</span>
                    <div className="mt-1.5 min-h-[72px] rounded-md border border-border bg-background px-3 py-2 text-sm leading-6">
                      您好，我是续费团队的客服小王，想和您确认一下之前咨询的事项，现在方便沟通吗？
                    </div>
                  </label>
                  <RecordingRow label="本人礼貌结束语" file="张琪｜礼貌结束语.wav" duration="00:04" updatedAt="今天 09:35 更新" />
                  <div className="flex items-start gap-2 text-[11px] leading-4 text-muted-foreground"><IconInfoCircle size={14} className="mt-0.5 shrink-0" />口头拒绝时播放本人结束语后挂机；客户已经主动挂机时不播放。开场白文案不影响外呼，只在转入人工时作为上下文。</div>
                </div>
                <SelectField label="兜底客服组" value="续费服务组" note="当前 2 位客服就绪，不含主客服本人" />
                <div>
                  <div className="text-xs font-medium">振铃并发数</div>
                  <div className="mt-1.5 flex h-10 items-center justify-between rounded-md border border-border bg-background px-1"><button className="grid h-8 w-8 place-items-center rounded text-lg text-muted-foreground">−</button><span className="font-mono text-sm font-semibold">4</span><button className="grid h-8 w-8 place-items-center rounded text-lg">＋</button></div>
                  <p className="mt-1 text-[11px] text-muted-foreground">范围 1–10；有人接听后立即停止补号</p>
                </div>
                <div className="col-span-2 flex items-center justify-between rounded-lg border border-success/25 bg-success/5 px-4 py-3">
                  <span className="flex items-center gap-2 text-xs font-medium"><span className="grid h-6 w-6 place-items-center rounded-full bg-success/10 text-success"><IconCheck size={14} /></span>启动条件已满足</span>
                  <span className="text-[11px] text-muted-foreground">Web 电话在线 · 两段录音有效 · 3 个预筛意图已启用 · 2 位兜底就绪</span>
                </div>
              </div>
            </section>

            <div className="flex min-h-0 flex-col gap-5">
              <section className="rounded-xl border border-border bg-card p-5">
                <h2 className="text-sm font-semibold">运行方式</h2>
                <div className="mt-5 space-y-4">
                  {[{ n: "01", t: "多路振铃", d: "最多同时保持 4 路拨号或振铃" }, { n: "02", t: "接听预筛", d: "任意客户接听后关闭补号闸门" }, { n: "03", t: "转入人工", d: "优先张琪，冲突时转续费服务组" }].map((item, index) => (
                    <div key={item.n} className="flex gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted font-mono text-[10px] font-semibold">{item.n}</span><div><div className="text-xs font-semibold">{item.t}</div><p className="mt-1 text-[11px] leading-4 text-muted-foreground">{item.d}</p></div>{index < 2 && <div className="hidden" />}</div>
                  ))}
                </div>
              </section>
              <section className="min-h-0 flex-1 rounded-xl border border-border bg-card p-5">
                <div className="flex items-center justify-between"><h2 className="text-sm font-semibold">兜底客服</h2><span className="rounded-md bg-success/10 px-2 py-1 text-[11px] font-medium text-success">2 人就绪</span></div>
                <div className="mt-4 space-y-3">
                  {[{ name: "李楠", state: "就绪", avatar: "李" }, { name: "陈默", state: "就绪", avatar: "陈" }, { name: "赵欣", state: "整理中", avatar: "赵" }].map((agent) => <div key={agent.name} className="flex items-center gap-3"><span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">{agent.avatar}</span><div className="flex-1 text-xs font-medium">{agent.name}</div><span className="flex items-center gap-1 text-[11px] text-muted-foreground"><span className={`h-1.5 w-1.5 rounded-full ${agent.state === "就绪" ? "bg-success" : "bg-warning"}`} />{agent.state}</span></div>)}
                </div>
                <div className="mt-5 flex gap-2 rounded-lg bg-muted/60 p-3 text-[11px] leading-4 text-muted-foreground"><IconUsers size={15} className="shrink-0" />若无人就绪，有效并发自动降为 1，不阻止主客服继续使用。</div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </PersonalOutboundWorkspaceShell>
  );
}

export function PersonalOutboundRecordingScreen() {
  return (
    <div className="relative h-full">
      <PersonalOutboundConfigScreen />
      <div className="absolute inset-0 z-40 flex items-center justify-center bg-foreground/30 backdrop-blur-[1px]">
        <section className="w-[520px] overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
          <div className="flex items-start justify-between border-b border-border px-5 py-4">
            <div><div className="flex items-center gap-2"><h2 className="font-display text-base font-bold">录制礼貌结束语</h2><span className="inline-flex items-center gap-1 rounded-md bg-destructive/10 px-2 py-1 text-[11px] font-medium text-destructive"><span className="h-1.5 w-1.5 rounded-full bg-destructive" />正在录制</span></div><p className="mt-1 text-xs text-muted-foreground">录制完成并保存后才会替换当前有效录音</p></div>
            <button className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground"><IconX size={17} /></button>
          </div>
          <div className="space-y-4 p-5">
            <div className="flex items-center justify-between rounded-lg border border-border bg-muted/35 px-3 py-2.5"><div className="flex items-center gap-2 text-xs"><IconMicrophone size={16} /><span className="font-medium">MacBook 麦克风</span></div><span className="flex items-center gap-1 text-[11px] text-success"><span className="h-1.5 w-1.5 rounded-full bg-success" />输入正常</span></div>
            <div className="rounded-lg bg-muted/60 p-3"><div className="text-[11px] font-medium text-muted-foreground">建议朗读</div><p className="mt-1.5 text-sm leading-6">好的，打扰您了，祝您生活愉快，再见。</p></div>
            <div className="rounded-xl border border-border px-4 py-5">
              <div className="flex h-16 items-center justify-center gap-1">{["h-3", "h-7", "h-10", "h-5", "h-12", "h-8", "h-14", "h-6", "h-11", "h-16", "h-9", "h-13", "h-7", "h-12", "h-5", "h-10", "h-6", "h-3"].map((heightClass, index) => <span key={index} className={`w-1 rounded-full bg-destructive/70 ${heightClass}`} />)}</div>
              <div className="mt-3 text-center"><span className="font-mono text-2xl font-semibold">00:04</span><span className="ml-2 text-xs text-muted-foreground">建议 2–8 秒 · 最长 30 秒</span></div>
            </div>
            <div className="flex items-center justify-between"><span className="text-[11px] text-muted-foreground">请在安静环境中录制，保持正常说话音量</span><button className="inline-flex h-9 items-center gap-2 rounded-md bg-destructive px-4 text-sm font-medium text-destructive-foreground"><IconPlayerStop size={15} />停止录制</button></div>
          </div>
        </section>
      </div>
    </div>
  );
}
