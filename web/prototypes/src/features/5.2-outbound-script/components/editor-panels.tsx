import {
  IconChevronDown,
  IconChevronRight,
  IconGitBranch,
  IconGripVertical,
  IconMessage,
  IconPlayerStop,
  IconRocket,
  IconTrash,
} from "@tabler/icons-react";
import { BRANCH_OPTIONS } from "../fixtures";

const TREE_ROWS = [
  { label: "开始", icon: IconRocket, depth: "pl-2" },
  { label: "确认接听人身份", icon: IconMessage, depth: "pl-6" },
  { label: "确认沟通意愿", icon: IconGitBranch, depth: "pl-10", active: true },
  { label: "介绍回访目的", icon: IconMessage, depth: "pl-14" },
  { label: "询问服务评价", icon: IconGitBranch, depth: "pl-[72px]" },
  { label: "约定回拨时间", icon: IconMessage, depth: "pl-14" },
  { label: "礼貌结束沟通", icon: IconPlayerStop, depth: "pl-14" },
];

export function NodeOutline() {
  return (
    <aside className="flex w-[248px] shrink-0 flex-col border-r border-border bg-background">
      <div className="border-b border-border px-4 py-3">
        <div className="text-sm font-semibold">节点目录</div>
        <div className="mt-1 text-xs text-muted-foreground">7 个节点 · 最大 4 层</div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {TREE_ROWS.map(({ label, icon: ItemIcon, depth, active }, index) => (
          <div key={label} className={`mb-0.5 flex h-9 items-center gap-1.5 rounded-md pr-2 text-xs ${depth} ${active ? "bg-muted font-semibold text-foreground" : "text-muted-foreground"}`}>
            {index < 3 ? <IconChevronDown size={12} /> : <IconChevronRight size={12} className="opacity-50" />}
            <ItemIcon size={14} />
            <span className="truncate">{label}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-border p-3 text-[11px] leading-5 text-muted-foreground">
        <div className="flex items-center justify-between"><span>节点上限</span><span className="font-mono">7 / 100</span></div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full w-[7%] rounded-full bg-primary" /></div>
      </div>
    </aside>
  );
}

function FieldBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="text-xs font-semibold">{label}</label><div className="mt-2">{children}</div></div>;
}

export function PropertyPanel() {
  return (
    <aside className="flex w-[354px] shrink-0 flex-col border-l border-border bg-background">
      <div className="border-b border-border px-5 py-3">
        <div className="flex items-center gap-2"><span className="rounded-md bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700">情景分支</span><span className="text-xs text-muted-foreground">已选中</span></div>
        <h3 className="mt-2 text-sm font-semibold">确认沟通意愿</h3>
      </div>
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
        <FieldBlock label="步骤标题">
          <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">确认沟通意愿</div>
        </FieldBlock>
        <FieldBlock label="建议话术">
          <div className="rounded-md border border-border">
            <div className="flex h-8 items-center gap-2 border-b border-border px-2 text-xs text-muted-foreground"><strong>B</strong><span className="italic">I</span><span>• 列表</span><span>链接</span></div>
            <div className="min-h-24 p-3 text-sm leading-6">想占用您两三分钟，对我们最近一次服务做个简单回访。请问您现在方便吗？</div>
          </div>
        </FieldBlock>
        <FieldBlock label="客服提示">
          <div className="min-h-16 rounded-md border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">客户不方便时不要继续追问，优先约定回拨时间。</div>
        </FieldBlock>
        <FieldBlock label="分支选项">
          <div className="space-y-2">
            {BRANCH_OPTIONS.map((option) => (
              <div key={option.label} className="rounded-lg border border-border bg-background p-2.5">
                <div className="flex items-center gap-2"><IconGripVertical size={14} className="text-muted-foreground" /><span className="flex-1 text-xs font-medium">{option.label}</span><IconTrash size={14} className="text-muted-foreground" /></div>
                <div className="mt-2 flex items-center gap-1.5 pl-5 text-[11px] text-muted-foreground"><IconChevronRight size={12} />后续：{option.next}</div>
              </div>
            ))}
          </div>
          <button className="mt-2 h-8 w-full rounded-md border border-dashed border-border text-xs text-muted-foreground">+ 添加分支选项</button>
        </FieldBlock>
      </div>
    </aside>
  );
}
