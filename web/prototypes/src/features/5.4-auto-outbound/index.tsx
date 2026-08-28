import type { ReactNode } from "react";
import { AutoOutboundListScreen } from "./screens/list";
import { CreateBasicInfoScreen, CreateModeScreen, CreateScheduleScreen } from "./screens/create";
import { AutoOutboundDetailScreen } from "./screens/detail";
import { AgentDispatchScreen, AgentWrapupScreen } from "./screens/agent";

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

export const AutoOutboundScreens: PrototypeScreen[] = [
  {
    id: "auto-outbound/list",
    title: "自动外呼任务 · 列表",
    description: "左侧二级子导航选中「自动外呼任务」；页头+筛选条+表格对齐现网人工外呼任务列表，含执行方式与「待拨」标识。",
    render: () => <Frame id="auto-outbound/list"><AutoOutboundListScreen /></Frame>,
  },
  {
    id: "auto-outbound/create-basic",
    title: "新建任务 · 基础信息",
    description: "步骤一：任务名称、任务模板、任务说明、负责人；展示从模板复制的字段结构预览。",
    render: () => <Frame id="auto-outbound/create-basic"><CreateBasicInfoScreen /></Frame>,
  },
  {
    id: "auto-outbound/create-mode",
    title: "新建任务 · 执行方式",
    description: "步骤二：IVR 语音流程 / 语音机器人 / 自动转人工三选一卡片；选中自动转人工时展开渐进式、比例多外呼与预测式配置。",
    render: () => <Frame id="auto-outbound/create-mode"><CreateModeScreen /></Frame>,
  },
  {
    id: "auto-outbound/create-schedule",
    title: "新建任务 · 外呼计划与呼叫策略",
    description: "步骤三：日期范围、每日呼叫时段多段配置、主叫号码、并发上限、按终态的重呼策略与单号码日频控。",
    render: () => <Frame id="auto-outbound/create-schedule"><CreateScheduleScreen /></Frame>,
  },
  {
    id: "auto-outbound/detail-targets",
    title: "任务详情 · 外呼对象",
    description: "机器人任务详情：概览指标、名单列表含状态自动流转与剩余重试次数，无坐席分配能力。",
    render: () => <Frame id="auto-outbound/detail-targets"><AutoOutboundDetailScreen tab="targets" /></Frame>,
  },
  {
    id: "auto-outbound/detail-records",
    title: "任务详情 · 呼叫记录",
    description: "按呼叫终态、接待方式与接待结果（意向标签、转人工标记）展示每次自动呼叫，可跳转通话详情。",
    render: () => <Frame id="auto-outbound/detail-records"><AutoOutboundDetailScreen tab="records" /></Frame>,
  },
  {
    id: "auto-outbound/detail-monitor",
    title: "任务详情 · 实时监控",
    description: "自动转人工任务专属 Tab：进行中呼叫、队列坐席状态、排队待接入与拨号强度、呼损率监控。",
    render: () => <Frame id="auto-outbound/detail-monitor"><AutoOutboundDetailScreen tab="monitor" /></Frame>,
  },
  {
    id: "auto-outbound/agent-dispatch",
    title: "坐席工作台 · 自动接听通话中",
    description: "三列弹屏对齐现网；右侧 Tab 在通话纪要/新建工单旁新增「外呼任务业务记录」，仅展示模板可编辑业务字段。",
    render: () => <Frame id="auto-outbound/agent-dispatch"><AgentDispatchScreen /></Frame>,
  },
  {
    id: "auto-outbound/agent-wrapup",
    title: "坐席工作台 · 话后处理",
    description: "整理态默认打开「外呼任务业务记录」Tab：模板业务字段与倒计时提交。",
    render: () => <Frame id="auto-outbound/agent-wrapup"><AgentWrapupScreen /></Frame>,
  },
];
