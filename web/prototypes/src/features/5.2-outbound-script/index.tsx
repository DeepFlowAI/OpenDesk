import type { ReactNode } from "react";
import { AgentScriptScreen } from "./screens/agent";
import { TemplateEditorScreen } from "./screens/template";

interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

function Frame({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">{id} · 1440×900</div>
    </div>
  );
}

export const OutboundScriptScreens: PrototypeScreen[] = [
  {
    id: "outbound-script/template-editor",
    title: "外呼话术 · 模板编辑器",
    description: "任务模板新增外呼话术 Tab，采用节点目录、树形画布和属性面板三栏布局。",
    render: () => <Frame id="outbound-script/template-editor"><TemplateEditorScreen /></Frame>,
  },
  {
    id: "outbound-script/template-preview",
    title: "外呼话术 · 管理端运行预览",
    description: "在编辑器上打开与坐席端一致的逐步话术抽屉，评审话术、提示和分支按钮层级。",
    render: () => <Frame id="outbound-script/template-preview"><TemplateEditorScreen preview /></Frame>,
  },
  {
    id: "outbound-script/agent-guided",
    title: "我的外呼对象 · 逐步话术",
    description: "客服选中外呼对象后打开话术抽屉，通话条保持可用，当前步骤突出建议话术与客户反馈分支。",
    render: () => <Frame id="outbound-script/agent-guided"><AgentScriptScreen mode="guided" /></Frame>,
  },
  {
    id: "outbound-script/agent-all-scripts",
    title: "我的外呼对象 · 全部话术",
    description: "客服偏离预设路径时，通过树形目录浏览完整话术并从指定步骤继续。",
    render: () => <Frame id="outbound-script/agent-all-scripts"><AgentScriptScreen mode="all" /></Frame>,
  },
];
