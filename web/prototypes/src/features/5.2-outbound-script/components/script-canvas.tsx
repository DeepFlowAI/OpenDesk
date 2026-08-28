import {
  IconArrowBackUp,
  IconArrowForwardUp,
  IconGitBranch,
  IconMessage,
  IconPlayerStop,
  IconRocket,
} from "@tabler/icons-react";
import { SCRIPT_NODES, type ScriptNodeKind } from "../fixtures";

const KIND_STYLE: Record<ScriptNodeKind, { label: string; icon: typeof IconRocket; tone: string }> = {
  start: { label: "开始", icon: IconRocket, tone: "bg-emerald-50 text-emerald-700" },
  script: { label: "话术", icon: IconMessage, tone: "bg-sky-50 text-sky-700" },
  branch: { label: "情景分支", icon: IconGitBranch, tone: "bg-amber-50 text-amber-700" },
  end: { label: "结束", icon: IconPlayerStop, tone: "bg-violet-50 text-violet-700" },
};

function NodeCard({ node }: { node: (typeof SCRIPT_NODES)[number] }) {
  const config = KIND_STYLE[node.kind];
  const NodeIcon = config.icon;
  return (
    <div className={`absolute w-[166px] rounded-xl border bg-background p-3 shadow-sm ${node.position} ${node.selected ? "border-primary ring-2 ring-primary/10" : "border-border"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${config.tone}`}>
          <NodeIcon size={11} /> {config.label}
        </span>
        {node.kind === "branch" && <span className="text-[10px] text-muted-foreground">3 个分支</span>}
      </div>
      <div className="mt-2 text-xs font-semibold">{node.title}</div>
      {node.caption && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground">{node.caption}</div>}
    </div>
  );
}

export function ScriptCanvas() {
  return (
    <div className="relative h-full min-w-[1020px] overflow-hidden bg-muted/40 [background-image:radial-gradient(var(--border)_1px,transparent_1px)] [background-size:20px_20px]">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <path d="M 154 244 C 174 244, 178 226, 198 226" fill="none" stroke="var(--border)" strokeWidth="2" />
        <path d="M 364 226 C 380 226, 380 226, 396 226" fill="none" stroke="var(--border)" strokeWidth="2" />
        <path d="M 562 214 C 584 214, 584 100, 610 100" fill="none" stroke="var(--border)" strokeWidth="2" />
        <path d="M 562 226 C 582 226, 586 244, 610 244" fill="none" stroke="var(--border)" strokeWidth="2" />
        <path d="M 562 238 C 582 238, 584 388, 610 388" fill="none" stroke="var(--border)" strokeWidth="2" />
        <path d="M 776 100 C 794 100, 806 100, 824 100" fill="none" stroke="var(--border)" strokeWidth="2" />
      </svg>
      {SCRIPT_NODES.map((node) => <NodeCard key={node.id} node={node} />)}
      <div className="absolute bottom-4 left-4 flex items-center gap-1 rounded-lg border border-border bg-background p-1 shadow-sm">
        <button className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground"><IconArrowBackUp size={15} /></button>
        <button className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground"><IconArrowForwardUp size={15} /></button>
        <span className="mx-1 h-4 w-px bg-border" />
        <button className="h-7 rounded-md px-2 text-[11px] text-muted-foreground">80%</button>
      </div>
    </div>
  );
}
